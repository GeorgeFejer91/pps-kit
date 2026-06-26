package io.ppskit.runnercompanion

import android.Manifest
import android.content.pm.PackageManager
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
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.Icons
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

class MainActivity : ComponentActivity() {
    private val runnerClient = RunnerClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initialPairing = PairingInfo.parseOrNull(intent?.dataString)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RunnerCompanionApp(initialPairing, runnerClient)
                }
            }
        }
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
    onUnpair: () -> Unit,
) {
    var participantName by remember(snapshot?.participantId) { mutableStateOf("") }
    var age by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.age.orEmpty()) }
    var handedness by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.handedness ?: "right") }
    var gender by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.gender ?: "prefer_not_to_say") }
    var shareName by remember(snapshot?.participantId) { mutableStateOf(snapshot?.setup?.nameSharingOptIn ?: false) }
    val participantCode = snapshot?.participantId.orEmpty()
    val block = snapshot?.activeBlock

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusChip(if (connected) "Online" else "Offline")
                StatusChip("Session ${pairing.sessionId}")
                StatusChip(if (snapshot?.setup?.ready == true) "Setup ready" else "Setup open")
                StatusChip(snapshot?.runStatus?.stateLabel?.ifBlank { "Ready" } ?: "Waiting")
            }
        }
        if (estimate.stale) {
            item {
                Text(
                    "Offline estimate",
                    color = MaterialTheme.colorScheme.error,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
        if (error.isNotBlank()) {
            item { Text(error, color = MaterialTheme.colorScheme.error) }
        }
        item {
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
                    enabled = snapshot?.canSubmitSetup() == true && participantName.isNotBlank() && age.isNotBlank(),
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Submit")
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(block?.blockLabel?.ifBlank { "Timeline" } ?: "Timeline", style = MaterialTheme.typography.titleMedium)
                val duration = block?.durationS ?: 0.0
                val progress = if (duration > 0.0) (estimate.elapsedS / duration).coerceIn(0.0, 1.0).toFloat() else 0f
                LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
                Text("${formatSeconds(estimate.elapsedS)} / ${formatSeconds(duration)}")
                Text("${snapshot?.timeline?.tactilePassed ?: 0} / ${snapshot?.timeline?.tactileTotal ?: 0} cues | ${snapshot?.timeline?.clicks ?: 0} clicks")
            }
        }
        item {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = { onStartPart(1) }, enabled = snapshot?.canStartPart(1) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 01")
                }
                Button(onClick = { onStartPart(2) }, enabled = snapshot?.canStartPart(2) == true) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Part 02")
                }
                Button(onClick = onContinue, enabled = snapshot?.canContinueInstruction() == true) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text(snapshot?.instructionGate?.buttonLabel?.ifBlank { "Continue" } ?: "Continue")
                }
            }
        }
        items(snapshot?.timeline?.trialRows ?: emptyList()) { row ->
            Text("${row.trialNumber}. ${row.label}  ${formatSeconds(row.startS)}-${formatSeconds(row.endS)}  ${row.noiseType}  ${row.soaMs}")
        }
        item {
            Button(onClick = onUnpair) {
                Text("Unpair")
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
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            PreviewView(ctx).also { previewView ->
                bindScanner(context, lifecycleOwner, previewView, onCode)
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
) {
    val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
    val executor = Executors.newSingleThreadExecutor()
    val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build(),
    )
    cameraProviderFuture.addListener(
        {
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(executor) { imageProxy ->
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return@setAnalyzer
                }
                val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
                scanner.process(image)
                    .addOnSuccessListener { barcodes ->
                        val value = barcodes.firstOrNull()?.rawValue
                        if (!value.isNullOrBlank()) {
                            onCode(value)
                        }
                    }
                    .addOnCompleteListener { imageProxy.close() }
            }
            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
        },
        ContextCompat.getMainExecutor(context),
    )
}

private fun formatSeconds(value: Double): String = String.format("%.1fs", value.coerceAtLeast(0.0))
