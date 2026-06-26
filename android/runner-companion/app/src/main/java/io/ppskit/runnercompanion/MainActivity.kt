package io.ppskit.runnercompanion

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Paint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.delay
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.abs
import kotlin.math.roundToInt

class MainActivity : ComponentActivity() {
    private val runnerClient = RunnerClient()
    private var latestPairing by mutableStateOf<PairingInfo?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        latestPairing = PairingInfo.parseOrNull(intent?.dataString)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RunnerCompanionApp(latestPairing, runnerClient)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        latestPairing = PairingInfo.parseOrNull(intent.dataString)
    }

    override fun onDestroy() {
        runnerClient.close()
        super.onDestroy()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RunnerCompanionApp(initialPairing: PairingInfo?, client: RunnerClient) {
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    var pairing by remember { mutableStateOf(initialPairing) }
    var snapshot by remember { mutableStateOf<RunnerSnapshot?>(null) }
    var connected by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var estimate by remember { mutableStateOf(EstimatedClock(0.0, stale = true, cappedAtBlockEnd = false)) }

    LaunchedEffect(initialPairing) {
        val incoming = initialPairing ?: return@LaunchedEffect
        pairing = incoming
        snapshot = null
        connected = false
        error = ""
    }

    LaunchedEffect(pairing) {
        val current = pairing ?: return@LaunchedEffect
        client.connect(
            current,
            onSnapshot = { incoming ->
                mainHandler.post {
                    snapshot = incoming
                    connected = true
                    error = ""
                }
            },
            onConnection = { state -> mainHandler.post { connected = state } },
            onError = { message -> mainHandler.post { error = message } },
        )
    }

    LaunchedEffect(snapshot, connected) {
        while (true) {
            estimate = ClockEstimator.estimate(snapshot, System.currentTimeMillis(), connected)
            delay(250)
        }
    }

    DisposableEffect(Unit) {
        onDispose { client.close() }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("PPS Runner Companion") })
        },
    ) { padding ->
        Box(modifier = Modifier.padding(padding)) {
            if (pairing == null) {
                PairingScreen(
                    error = error,
                    onPair = { raw ->
                        runCatching { PairingInfo.parse(raw) }
                            .onSuccess {
                                pairing = it
                                error = ""
                            }
                            .onFailure { error = it.message ?: "Pairing failed." }
                    },
                )
            } else {
                RunnerScreen(
                    pairing = pairing!!,
                    snapshot = snapshot,
                    connected = connected,
                    error = error,
                    estimate = estimate,
                    onSubmitSetup = { payload ->
                        client.submitSetup(
                            payload,
                            onSnapshot = { incoming -> mainHandler.post { snapshot = incoming } },
                            onError = { message -> mainHandler.post { error = message } },
                        )
                    },
                    onContinue = {
                        client.continueInstruction(
                            onSnapshot = { incoming -> mainHandler.post { snapshot = incoming } },
                            onError = { message -> mainHandler.post { error = message } },
                        )
                    },
                    onStartPart = { part ->
                        client.startPart(
                            part,
                            onSnapshot = { incoming -> mainHandler.post { snapshot = incoming } },
                            onError = { message -> mainHandler.post { error = message } },
                        )
                    },
                    onPause = {
                        client.pause(
                            onSnapshot = { incoming -> mainHandler.post { snapshot = incoming } },
                            onError = { message -> mainHandler.post { error = message } },
                        )
                    },
                    onResume = {
                        client.resume(
                            onSnapshot = { incoming -> mainHandler.post { snapshot = incoming } },
                            onError = { message -> mainHandler.post { error = message } },
                        )
                    },
                    onUnpair = {
                        client.close()
                        pairing = null
                        snapshot = null
                        connected = false
                    },
                )
            }
        }
    }
}

@Composable
private fun PairingScreen(error: String, onPair: (String) -> Unit) {
    val context = LocalContext.current
    var rawUri by remember { mutableStateOf("") }
    var scannerVisible by remember { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        scannerVisible = granted
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Pair runner", style = MaterialTheme.typography.headlineMedium)
        OutlinedTextField(
            value = rawUri,
            onValueChange = { rawUri = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = false,
            label = { Text("Pairing URI") },
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = {
                val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                if (granted) scannerVisible = true else permissionLauncher.launch(Manifest.permission.CAMERA)
            }) {
                Icon(Icons.Default.QrCodeScanner, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text("Scan")
            }
            Button(onClick = { onPair(rawUri) }, enabled = rawUri.isNotBlank()) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text("Pair")
            }
        }
        if (error.isNotBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error)
        }
        if (scannerVisible) {
            QrScanner(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(320.dp),
                onCode = {
                    scannerVisible = false
                    rawUri = it
                    onPair(it)
                },
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RunnerScreen(
    pairing: PairingInfo,
    snapshot: RunnerSnapshot?,
    connected: Boolean,
    error: String,
    estimate: EstimatedClock,
    onSubmitSetup: (SetupPayload) -> Unit,
    onContinue: () -> Unit,
    onStartPart: (Int) -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onUnpair: () -> Unit,
) {
    var participantName by remember(snapshot?.participantId) { mutableStateOf("") }
    var age by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.age.orEmpty()) }
    var handedness by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.handedness ?: "right") }
    var gender by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.gender ?: "prefer_not_to_say") }
    var shareName by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.nameSharingOptIn ?: false) }
    val participantCode = snapshot?.participantId.orEmpty()
    val block = snapshot?.activeBlock
    val setupVisible = snapshot?.setup?.ready != true
    val pauseEnabled = connected && snapshot?.canPause() == true
    val resumeEnabled = connected && snapshot?.canResume() == true

    val controls: @Composable (Modifier) -> Unit = { panelModifier ->
        Column(
            modifier = panelModifier
                .padding(12.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusChip(if (connected) "Online" else "Offline")
                StatusChip("Session ${pairing.sessionId}")
                StatusChip(if (snapshot?.setup?.ready == true) "Setup ready" else "Setup open")
                StatusChip(snapshot?.runStatus?.stateLabel?.ifBlank { "Ready" } ?: "Waiting")
            }
            if (estimate.stale) {
                Text(
                    "Offline estimate",
                    color = MaterialTheme.colorScheme.error,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            if (error.isNotBlank()) {
                Text(error, color = MaterialTheme.colorScheme.error)
            }
            if (setupVisible) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Participant Setup", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        value = participantName,
                        onValueChange = { participantName = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Name") },
                        enabled = snapshot?.runStatus?.running != true,
                    )
                    OutlinedTextField(
                        value = age,
                        onValueChange = { age = it.filter(Char::isDigit) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Age") },
                        enabled = snapshot?.runStatus?.running != true,
                    )
                    ChoiceRow("Handedness", handedness, listOf("right", "left", "ambidextrous", "prefer_not_to_say")) { handedness = it }
                    ChoiceRow("Gender", gender, listOf("male", "female", "other", "prefer_not_to_say")) { gender = it }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = shareName, onCheckedChange = { shareName = it })
                        Text("Name sharing opt-in")
                    }
                    Button(
                        onClick = {
                            onSubmitSetup(
                                SetupPayload(
                                    participantCode = participantCode,
                                    participantName = participantName,
                                    age = age,
                                    handedness = handedness,
                                    gender = gender,
                                    nameSharingOptIn = shareName,
                                )
                            )
                        },
                        enabled = connected && snapshot?.canSubmitSetup() == true && participantName.isNotBlank() && age.isNotBlank(),
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                        Spacer(Modifier.padding(3.dp))
                        Text("Submit")
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onPause,
                    enabled = pauseEnabled,
                ) {
                    Icon(Icons.Default.Pause, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Pause")
                }
                Button(
                    onClick = onResume,
                    enabled = resumeEnabled,
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Resume")
                }
                Button(onClick = onContinue, enabled = connected && snapshot?.canContinueInstruction() == true) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text(snapshot?.instructionGate?.buttonLabel?.ifBlank { "Continue" } ?: "Continue")
                }
                Button(onClick = { onStartPart(1) }, enabled = connected && snapshot?.canStartPart(1) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 01")
                }
                Button(onClick = { onStartPart(2) }, enabled = connected && snapshot?.canStartPart(2) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 02")
                }
            }
            OutlinedButton(onClick = onUnpair) {
                Text("Unpair")
            }
        }
    }

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
    ) {
        if (maxWidth > maxHeight && !setupVisible) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LandscapeCommandStrip(
                    pairing = pairing,
                    snapshot = snapshot,
                    connected = connected,
                    error = error,
                    estimate = estimate,
                    onContinue = onContinue,
                    onStartPart = onStartPart,
                    onPause = onPause,
                    onResume = onResume,
                    modifier = Modifier.fillMaxWidth(),
                )
                LiveFeedbackPanel(
                    snapshot = snapshot,
                    estimate = estimate,
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    expandedTimeline = true,
                )
            }
        } else if (maxWidth > maxHeight) {
            Row(
                modifier = Modifier.fillMaxSize(),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                controls(Modifier.width(320.dp).fillMaxHeight())
                LiveFeedbackPanel(
                    snapshot = snapshot,
                    estimate = estimate,
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .padding(vertical = 12.dp),
                )
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                controls(Modifier.fillMaxWidth())
                LiveFeedbackPanel(
                    snapshot = snapshot,
                    estimate = estimate,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LandscapeCommandStrip(
    pairing: PairingInfo,
    snapshot: RunnerSnapshot?,
    connected: Boolean,
    error: String,
    estimate: EstimatedClock,
    onContinue: () -> Unit,
    onStartPart: (Int) -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.heightIn(min = 84.dp, max = 128.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FlowRow(
                modifier = Modifier.weight(1f),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                StatusChip(if (connected) "Online" else "Offline")
                StatusChip("Session ${pairing.sessionId}")
                StatusChip(if (snapshot?.setup?.ready == true) "Setup ready" else "Setup open")
                StatusChip(snapshot?.runStatus?.stateLabel?.ifBlank { "Ready" } ?: "Waiting")
                if (estimate.stale) {
                    StatusChip("Offline estimate")
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = onPause, enabled = connected && snapshot?.canPause() == true) {
                    Icon(Icons.Default.Pause, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Pause")
                }
                Button(onClick = onResume, enabled = connected && snapshot?.canResume() == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Resume")
                }
                Button(onClick = onContinue, enabled = connected && snapshot?.canContinueInstruction() == true) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text(snapshot?.instructionGate?.buttonLabel?.ifBlank { "Continue" } ?: "Continue")
                }
                Button(onClick = { onStartPart(1) }, enabled = connected && snapshot?.canStartPart(1) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 01")
                }
                Button(onClick = { onStartPart(2) }, enabled = connected && snapshot?.canStartPart(2) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 02")
                }
            }
        }
        if (error.isNotBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LiveFeedbackPanel(
    snapshot: RunnerSnapshot?,
    estimate: EstimatedClock,
    modifier: Modifier = Modifier,
    expandedTimeline: Boolean = false,
) {
    val block = snapshot?.activeBlock
    val duration = block?.durationS ?: 0.0
    val progress = if (duration > 0.0) (estimate.elapsedS / duration).coerceIn(0.0, 1.0).toFloat() else 0f
    BoxWithConstraints(modifier = modifier) {
        val compactLandscape = expandedTimeline && maxHeight < 420.dp
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(if (compactLandscape) 6.dp else 10.dp),
        ) {
            if (!compactLandscape) {
                Text("Live Feedback", style = MaterialTheme.typography.titleLarge)
            }
            Text(
                listOfNotNull(block?.phaseLabel?.takeIf { it.isNotBlank() }, block?.blockLabel?.takeIf { it.isNotBlank() })
                    .joinToString(" - ")
                    .ifBlank { "No active block" },
                style = if (compactLandscape) MaterialTheme.typography.titleSmall else MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
            if (!compactLandscape) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusChip("${formatSeconds(estimate.elapsedS)} / ${formatSeconds(duration)}")
                    StatusChip("${snapshot?.timeline?.tactilePassed ?: 0} / ${snapshot?.timeline?.tactileTotal ?: 0} cues")
                    StatusChip("${snapshot?.timeline?.clicks ?: 0} clicks")
                    StatusChip(snapshot?.runStatus?.stateLabel?.ifBlank { if (snapshot?.runStatus?.paused == true || block?.paused == true) "Paused" else "Waiting" } ?: "Waiting")
                }
            }
            val timelineModifier = if (expandedTimeline) {
                Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .heightIn(min = if (compactLandscape) 136.dp else 220.dp)
            } else {
                Modifier
                    .fillMaxWidth()
                    .height(260.dp)
            }
            BlockTimelineCanvas(snapshot = snapshot, estimate = estimate, modifier = timelineModifier)
            if (!compactLandscape) {
                ResponseTimingStrip(snapshot = snapshot)
            }
        }
    }
}

@Composable
private fun BlockTimelineCanvas(
    snapshot: RunnerSnapshot?,
    estimate: EstimatedClock,
    modifier: Modifier = Modifier,
) {
    val timeline = snapshot?.timeline
    val trials = timeline?.trialRows.orEmpty()
    val cues = timeline?.tactileCues.orEmpty()
    val clicks = timeline?.clickMarkers.orEmpty()
    val maxTrialEnd = trials.maxOfOrNull { it.endS } ?: 0.0
    val maxCueTime = cues.maxOfOrNull { it.timeS } ?: 0.0
    val maxClickTime = clicks.maxOfOrNull { it.timeS } ?: 0.0
    val duration = TimelineLayoutModel.resolveDuration(
        snapshot?.activeBlock?.durationS ?: 0.0,
        maxTrialEnd,
        maxCueTime,
        maxClickTime,
        estimate.elapsedS,
        1.0,
    )
    val cueById = cues.associateBy { it.cueId }
    val cueSoaByTrialUid = cues
        .filter { it.trialUid.isNotBlank() && it.soaMs.isNotBlank() }
        .groupBy { it.trialUid }
        .mapValues { (_, trialCues) -> trialCues.first().soaMs }
    val background = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
    val axis = MaterialTheme.colorScheme.outline
    val text = MaterialTheme.colorScheme.onSurface
    val annotationText = MaterialTheme.colorScheme.onSurfaceVariant
    val trialPalette = listOf(
        Color(0xFFE8F1F2),
        Color(0xFFF4EEE2),
        Color(0xFFECEAF4),
        Color(0xFFE7F0E6),
    )
    val cueUpcoming = MaterialTheme.colorScheme.primary
    val cuePassed = Color(0xFF247A52)
    val clickValid = Color(0xFF16834A)
    val clickOffCue = Color(0xFFD06722)
    val playhead = Color(0xFFD32F2F)

    Canvas(modifier = modifier) {
        drawRoundRect(
            color = background,
            topLeft = Offset.Zero,
            size = Size(size.width, size.height),
            cornerRadius = CornerRadius(8.dp.toPx()),
        )
        val left = 58.dp.toPx()
        val right = (size.width - 18.dp.toPx()).coerceAtLeast(left + 1.dp.toPx())
        val plotWidth = (right - left).coerceAtLeast(1f)
        val top = 18.dp.toPx()
        val bottom = size.height - 26.dp.toPx()
        val usableHeight = (bottom - top).coerceAtLeast(90.dp.toPx())
        val laneGap = usableHeight / 3f
        val trialTop = top + 10.dp.toPx()
        val trialHeight = minOf(46.dp.toPx(), laneGap * 0.58f)
        val tactileY = top + laneGap * 1.55f
        val clickY = top + laneGap * 2.55f
        val hasAnnotationSpace = laneGap >= 30.dp.toPx()
        val cueHalfHeight = minOf(20.dp.toPx(), laneGap * if (hasAnnotationSpace) 0.24f else 0.34f)
        val soaY = ((trialTop + trialHeight) + (tactileY - cueHalfHeight)) / 2f + 4.dp.toPx()
        val rtY = ((tactileY + cueHalfHeight) + clickY) / 2f - 2.dp.toPx()
        fun xFor(seconds: Double): Float = left + ((seconds / duration).coerceIn(0.0, 1.0).toFloat() * plotWidth)

        val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = text.toArgb()
            textSize = 11.dp.toPx()
            textAlign = Paint.Align.RIGHT
        }
        val itemPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = text.toArgb()
            textSize = 10.dp.toPx()
            textAlign = Paint.Align.LEFT
        }
        val axisPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = axis.toArgb()
            textSize = 10.dp.toPx()
            textAlign = Paint.Align.CENTER
        }
        val annotationPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = annotationText.toArgb()
            textSize = 9.dp.toPx()
            textAlign = Paint.Align.CENTER
        }
        val rtPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = clickValid.toArgb()
            textSize = 9.dp.toPx()
            textAlign = Paint.Align.CENTER
            isFakeBoldText = true
        }
        if (trials.isEmpty() && cues.isEmpty() && clicks.isEmpty()) {
            val placeholderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = text.copy(alpha = 0.72f).toArgb()
                textSize = 14.dp.toPx()
                textAlign = Paint.Align.CENTER
            }
            drawContext.canvas.nativeCanvas.drawText(
                "Waiting for block timeline",
                size.width / 2f,
                size.height / 2f,
                placeholderPaint,
            )
            return@Canvas
        }

        drawLine(axis, Offset(left, bottom), Offset(right, bottom), strokeWidth = 1.dp.toPx())
        val ticks = TimelineLayoutModel.ticks(duration, plotWidth)
        ticks.forEach { tick ->
            val x = xFor(tick.seconds)
            drawLine(axis.copy(alpha = 0.35f), Offset(x, top), Offset(x, bottom), strokeWidth = 1.dp.toPx())
            drawContext.canvas.nativeCanvas.drawText(tick.label, x, size.height - 8.dp.toPx(), axisPaint)
        }
        drawContext.canvas.nativeCanvas.drawText("Trials", left - 8.dp.toPx(), trialTop + trialHeight * 0.67f, labelPaint)
        if (hasAnnotationSpace) {
            drawContext.canvas.nativeCanvas.drawText("SOA", left - 8.dp.toPx(), soaY, labelPaint)
        }
        drawContext.canvas.nativeCanvas.drawText("Tactile", left - 8.dp.toPx(), tactileY + 4.dp.toPx(), labelPaint)
        if (hasAnnotationSpace && TimelineLayoutModel.shouldShowEventAnnotations(clicks.count { it.rtS != null }, plotWidth)) {
            drawContext.canvas.nativeCanvas.drawText("RT", left - 8.dp.toPx(), rtY, labelPaint)
        }
        drawContext.canvas.nativeCanvas.drawText("Clicks", left - 8.dp.toPx(), clickY + 4.dp.toPx(), labelPaint)
        val densityStyle = TimelineLayoutModel.densityStyle(cues.size + clicks.size, plotWidth)
        val cueRadius = 5.dp.toPx() * densityStyle.markerScale
        val nextCueRadius = 9.dp.toPx() * densityStyle.markerScale.coerceAtLeast(0.7f)
        val clickRadius = 6.dp.toPx() * densityStyle.markerScale
        val clickInnerRadius = 2.dp.toPx() * densityStyle.markerScale.coerceAtLeast(0.7f)

        trials.forEachIndexed { index, trial ->
            val startX = xFor(trial.startS)
            val endX = xFor(trial.endS).coerceAtLeast(startX + 2.dp.toPx())
            val color = trialPalette[index % trialPalette.size]
            drawRoundRect(
                color = color,
                topLeft = Offset(startX, trialTop),
                size = Size(endX - startX, trialHeight),
                cornerRadius = CornerRadius(6.dp.toPx()),
            )
            drawRoundRect(
                color = axis.copy(alpha = 0.45f),
                topLeft = Offset(startX, trialTop),
                size = Size(endX - startX, trialHeight),
                cornerRadius = CornerRadius(6.dp.toPx()),
                style = Stroke(width = 1.dp.toPx()),
            )
            if (TimelineLayoutModel.shouldShowTrialLabel(trial.startS, trial.endS, duration, plotWidth)) {
                val label = trial.label.ifBlank { trial.noiseType.ifBlank { "Trial ${trial.trialNumber}" } }.take(18)
                drawContext.canvas.nativeCanvas.drawText(label, startX + 5.dp.toPx(), trialTop + trialHeight * 0.62f, itemPaint)
            }
        }

        cues.forEach { cue ->
            val x = xFor(cue.timeS)
            val color = when (cue.status) {
                "passed" -> cuePassed
                "next", "recentered" -> cueUpcoming
                else -> axis
            }
            drawLine(color.copy(alpha = 0.8f), Offset(x, tactileY - cueHalfHeight), Offset(x, tactileY + cueHalfHeight), strokeWidth = (2.dp.toPx() * densityStyle.markerScale).coerceAtLeast(1.dp.toPx()))
            drawCircle(color, radius = cueRadius, center = Offset(x, tactileY))
            if (cue.status == "next") {
                drawCircle(color, radius = nextCueRadius, center = Offset(x, tactileY), style = Stroke(width = 2.dp.toPx()))
            }
        }

        clicks.forEach { click ->
            val x = xFor(click.timeS)
            val valid = click.responseStatus == "tactile_response"
            val color = if (valid) clickValid else clickOffCue
            val cue = click.cueId?.let { cueById[it] }
            if (cue != null && densityStyle.drawCueClickConnectors) {
                val cueX = xFor(cue.timeS)
                drawLine(color.copy(alpha = 0.75f), Offset(cueX, tactileY + 12.dp.toPx()), Offset(x, clickY - 8.dp.toPx()), strokeWidth = 2.dp.toPx())
            }
            drawCircle(color, radius = clickRadius, center = Offset(x, clickY))
            drawCircle(Color.White.copy(alpha = 0.85f), radius = clickInnerRadius, center = Offset(x, clickY))
        }

        val currentX = xFor(estimate.elapsedS)
        drawLine(playhead, Offset(currentX, top), Offset(currentX, bottom), strokeWidth = 3.dp.toPx())

        if (hasAnnotationSpace) {
            trials.forEach { trial ->
                if (!TimelineLayoutModel.shouldShowIntervalAnnotation(trial.startS, trial.endS, duration, plotWidth)) {
                    return@forEach
                }
                val startX = xFor(trial.startS)
                val endX = xFor(trial.endS).coerceAtLeast(startX + 2.dp.toPx())
                val soaLabel = formatSoaValue(trial.soaMs.ifBlank { cueSoaByTrialUid[trial.trialUid].orEmpty() })
                if (soaLabel.isBlank()) return@forEach
                val width = endX - startX
                val horizontalPadding = 6.dp.toPx()
                val compactLabel = compactSoaValue(soaLabel)
                val labelToDraw = when {
                    annotationPaint.measureText(soaLabel) <= width - horizontalPadding -> soaLabel
                    compactLabel.isNotBlank() && annotationPaint.measureText(compactLabel) <= width - horizontalPadding -> compactLabel
                    else -> ""
                }
                if (labelToDraw.isNotBlank()) {
                    drawContext.canvas.nativeCanvas.drawText(labelToDraw, (startX + endX) / 2f, soaY, annotationPaint)
                }
            }
        }

        if (hasAnnotationSpace && TimelineLayoutModel.shouldShowEventAnnotations(clicks.count { it.rtS != null }, plotWidth)) {
            var lastLabelRight = Float.NEGATIVE_INFINITY
            val labelGap = 4.dp.toPx()
            clicks.forEach { click ->
                val rt = click.rtS ?: return@forEach
                val label = formatMilliseconds(rt)
                val labelWidth = rtPaint.measureText(label)
                if (labelWidth >= plotWidth) return@forEach
                val centerX = xFor(click.timeS).coerceIn(left + labelWidth / 2f, right - labelWidth / 2f)
                val labelLeft = centerX - labelWidth / 2f
                val labelRight = centerX + labelWidth / 2f
                if (labelLeft > lastLabelRight + labelGap) {
                    drawContext.canvas.nativeCanvas.drawText(label, centerX, rtY, rtPaint)
                    lastLabelRight = labelRight
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ResponseTimingStrip(snapshot: RunnerSnapshot?) {
    val clicks = snapshot?.timeline?.clickMarkers.orEmpty().takeLast(6).reversed()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Reaction Times", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (clicks.isEmpty()) {
                StatusChip("Waiting for clicks")
            } else {
                clicks.forEach { click ->
                    val rt = click.rtS?.let { formatMilliseconds(it) } ?: "off cue"
                    StatusChip("#${click.clickId} $rt")
                }
            }
        }
    }
}

@Composable
private fun StatusChip(label: String) {
    AssistChip(onClick = {}, label = { Text(label) })
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoiceRow(label: String, selected: String, options: List<String>, onSelected: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { option ->
                FilterChip(
                    selected = selected == option,
                    onClick = { onSelected(option) },
                    label = { Text(option.replace("_", " ")) },
                )
            }
        }
    }
}

@Composable
private fun QrScanner(modifier: Modifier = Modifier, onCode: (String) -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val cleanupRef = remember { AtomicReference<(() -> Unit)?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            cleanupRef.getAndSet(null)?.invoke()
        }
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            PreviewView(ctx).also { previewView ->
                cleanupRef.set(bindScanner(context, lifecycleOwner, previewView, onCode))
            }
        },
    )
}

@androidx.annotation.OptIn(ExperimentalGetImage::class)
private fun bindScanner(
    context: android.content.Context,
    lifecycleOwner: androidx.lifecycle.LifecycleOwner,
    previewView: PreviewView,
    onCode: (String) -> Unit,
): () -> Unit {
    val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
    val executor = Executors.newSingleThreadExecutor()
    val mainExecutor = ContextCompat.getMainExecutor(context)
    val active = AtomicBoolean(true)
    val delivered = AtomicBoolean(false)
    val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build(),
    )
    cameraProviderFuture.addListener(
        {
            if (!active.get()) {
                return@addListener
            }
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(executor) { imageProxy ->
                if (!active.get()) {
                    imageProxy.close()
                    return@setAnalyzer
                }
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return@setAnalyzer
                }
                val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
                scanner.process(image)
                    .addOnSuccessListener(mainExecutor) { barcodes ->
                        val value = barcodes.firstOrNull()?.rawValue
                        if (!value.isNullOrBlank() && delivered.compareAndSet(false, true)) {
                            active.set(false)
                            onCode(value)
                        }
                    }
                    .addOnCompleteListener { imageProxy.close() }
            }
            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
        },
        mainExecutor,
    )
    return {
        active.set(false)
        runCatching {
            if (cameraProviderFuture.isDone) {
                cameraProviderFuture.get().unbindAll()
            }
        }
        runCatching { scanner.close() }
        executor.shutdownNow()
    }
}

private fun formatSeconds(value: Double): String = TimelineLayoutModel.formatTime(value)

private fun formatMilliseconds(valueS: Double): String = "${(valueS.coerceAtLeast(0.0) * 1000.0).toInt()} ms"

private fun formatSoaValue(value: String): String {
    val clean = value.trim()
    if (clean.isBlank() || clean.equals("nan", ignoreCase = true)) return ""
    if (clean.equals("n/a", ignoreCase = true) || clean.equals("na", ignoreCase = true)) return "N/A"
    val numericText = clean.replace(Regex("\\s*ms\\s*$", RegexOption.IGNORE_CASE), "").trim()
    val numeric = numericText.toDoubleOrNull()
    if (numeric != null) {
        val rounded = numeric.roundToInt()
        return if (abs(numeric - rounded) < 0.05) {
            "$rounded ms"
        } else {
            String.format("%.1f ms", numeric)
        }
    }
    return clean.take(12)
}

private fun compactSoaValue(value: String): String =
    value.removeSuffix(" ms").takeIf { it != value && it.isNotBlank() } ?: value.take(6)
