package io.ppskit.runnercompanion

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Paint
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
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
import androidx.compose.material.icons.filled.Search
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
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

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

private enum class CompanionMode {
    PcRunnerControl,
    RunExperimentOnPhone,
}

private enum class PhoneRuntimeRole {
    Runner,
    Controller,
}

private fun modeForPairing(pairing: PairingInfo): CompanionMode? =
    if (pairing.isPhoneExport) CompanionMode.RunExperimentOnPhone else null

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RunnerCompanionApp(initialPairing: PairingInfo?, client: RunnerClient) {
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    var pairing by remember { mutableStateOf(initialPairing) }
    var snapshot by remember { mutableStateOf<RunnerSnapshot?>(null) }
    var connected by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var estimate by remember { mutableStateOf(EstimatedClock(0.0, stale = true, cappedAtBlockEnd = false)) }
    var mode by remember { mutableStateOf<CompanionMode?>(initialPairing?.let { modeForPairing(it) }) }

    LaunchedEffect(initialPairing) {
        val incoming = initialPairing ?: return@LaunchedEffect
        pairing = incoming
        snapshot = null
        connected = false
        error = ""
        mode = modeForPairing(incoming)
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
                                mode = modeForPairing(it)
                                error = ""
                            }
                            .onFailure { error = it.message ?: "Pairing failed." }
                    },
                )
            } else {
                val currentPairing = pairing!!
                when (mode) {
                    null -> ModeSelectionScreen(
                        pairing = currentPairing,
                        connected = connected,
                        error = error,
                        snapshot = snapshot,
                        onMode = { selected -> mode = selected },
                        onUnpair = {
                            client.close()
                            pairing = null
                            snapshot = null
                            connected = false
                            mode = null
                        },
                    )
                    CompanionMode.PcRunnerControl -> RunnerScreen(
                        pairing = currentPairing,
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
                        onChooseMode = { mode = null },
                        onUnpair = {
                            client.close()
                            pairing = null
                            snapshot = null
                            connected = false
                            mode = null
                        },
                    )
                    CompanionMode.RunExperimentOnPhone -> PhoneRuntimeScreen(
                        pairing = currentPairing,
                        client = client,
                        connected = connected,
                        mainHandler = mainHandler,
                        onChooseMode = { mode = null },
                        onUnpair = {
                            client.close()
                            pairing = null
                            snapshot = null
                            connected = false
                            mode = null
                        },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ModeSelectionScreen(
    pairing: PairingInfo,
    connected: Boolean,
    error: String,
    snapshot: RunnerSnapshot?,
    onMode: (CompanionMode) -> Unit,
    onUnpair: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Experiment Mode", style = MaterialTheme.typography.headlineMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusChip(if (connected) "Online" else "Offline")
            StatusChip("Session ${pairing.sessionId}")
            StatusChip(snapshot?.participantId?.ifBlank { "Participant" } ?: "Participant")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = { onMode(CompanionMode.PcRunnerControl) }) {
                Icon(Icons.Default.PlayArrow, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text("PC Runner Control")
            }
            Button(onClick = { onMode(CompanionMode.RunExperimentOnPhone) }, enabled = connected) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text("Run Experiment On Phone")
            }
        }
        OutlinedButton(onClick = onUnpair) {
            Text("Unpair")
        }
        if (error.isNotBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun PairingScreen(error: String, onPair: (String) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var rawUri by remember { mutableStateOf("") }
    var scannerVisible by remember { mutableStateOf(false) }
    var discoveryStatus by remember { mutableStateOf("") }
    var discovering by remember { mutableStateOf(false) }
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
            OutlinedButton(
                onClick = {
                    discovering = true
                    discoveryStatus = "Listening"
                    scope.launch {
                        val discovered = runCatching { listenForCompanionDiscoveryOnce(context) }
                        val advertisement = discovered.getOrNull()
                        discoveryStatus = when {
                            advertisement != null -> "Found ${advertisement.endpointLabel} (${advertisement.transport})"
                            discovered.isFailure -> discovered.exceptionOrNull()?.message ?: "Discovery failed"
                            else -> "No runner found"
                        }
                        discovering = false
                    }
                },
                enabled = !discovering,
            ) {
                Icon(Icons.Default.Search, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text(if (discovering) "Listening" else "Discover")
            }
            Button(onClick = { onPair(rawUri) }, enabled = rawUri.isNotBlank()) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text("Pair")
            }
        }
        if (discoveryStatus.isNotBlank()) {
            Text(discoveryStatus, style = MaterialTheme.typography.bodyMedium)
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
private fun PhoneRuntimeScreen(
    pairing: PairingInfo,
    client: RunnerClient,
    connected: Boolean,
    mainHandler: Handler,
    onChooseMode: () -> Unit,
    onUnpair: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var packages by remember { mutableStateOf<List<MobilePackageSummary>>(emptyList()) }
    var selectedPackageId by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("Ready") }
    var error by remember { mutableStateOf("") }
    var syncing by remember { mutableStateOf(false) }
    var running by remember { mutableStateOf(false) }
    var activeBlockLabel by remember { mutableStateOf("") }
    var runProgress by remember { mutableStateOf("") }
    var uploadedArtifact by remember { mutableStateOf("") }
    var lastRunDir by remember { mutableStateOf("") }
    var controllerSending by remember { mutableStateOf(false) }
    var phoneAge by remember(pairing.sessionId) { mutableStateOf("") }
    var phoneHandedness by remember(pairing.sessionId) { mutableStateOf("right") }
    var phoneGender by remember(pairing.sessionId) { mutableStateOf("prefer_not_to_say") }
    var tactileThreshold by remember(pairing.sessionId) { mutableStateOf("") }
    var hapticCalibration by remember(pairing.sessionId) { mutableStateOf<JSONObject?>(null) }
    var hapticCalibrationSession by remember(pairing.sessionId) { mutableStateOf<PhoneHapticCalibrationSession?>(null) }
    var hapticCalibrationStatus by remember(pairing.sessionId) { mutableStateOf("") }
    var phoneRole by remember(pairing.sessionId) { mutableStateOf(PhoneRuntimeRole.Runner) }
    var session by remember { mutableStateOf<PhoneRunSession?>(null) }
    val nativeRunnerBridge = remember(pairing.sessionId) { PhoneNativeLslBridgeFactory.create() }
    val nativeControllerBridge = remember(pairing.sessionId) { PhoneNativeLslBridgeFactory.create() }
    var idleRunnerCommandStatus by remember(pairing.sessionId) { mutableStateOf<PhoneNativeLslBridgeStatus?>(null) }
    var controllerTransport by remember(pairing.sessionId) { mutableStateOf<PhoneLslControllerTransport?>(null) }
    var runJob by remember { mutableStateOf<Job?>(null) }
    val logLines = remember { mutableStateListOf<String>() }
    val syncedPackages = remember { mutableStateMapOf<String, MobileRunPackage>() }
    val hapticCapability = remember(hapticCalibration?.toString().orEmpty()) { phoneHapticCapability(context, hapticCalibration) }

    fun log(message: String) {
        logLines.add(0, message)
        while (logLines.size > 8) logLines.removeAt(logLines.lastIndex)
    }

    fun applyHapticCalibrationResult(result: PhoneHapticCalibrationResult) {
        val artifact = result.toJson()
        hapticCalibration = artifact
        val recommended = result.recommendedThresholdPercent
        if (recommended != null) {
            tactileThreshold = recommended.toString()
        }
        hapticCalibrationStatus = when (result.status) {
            "threshold_detected" -> "Threshold ${recommended ?: "N/A"}%"
            "binary_detected" -> "Binary vibration detected"
            "not_detected_at_max" -> "Not detected at max"
            "no_vibrator" -> "No vibrator"
            else -> result.status
        }
        log("Haptic calibration ${result.status}")
    }

    fun refreshPackages() {
        client.listMobilePackages(
            onPackages = { listing ->
                mainHandler.post {
                    packages = listing.packages
                    selectedPackageId = listing.activePackageId.ifBlank { listing.packages.firstOrNull()?.packageId.orEmpty() }
                    syncedPackages.keys.retainAll(listing.packages.map { it.packageId }.toSet())
                    status = if (listing.packages.isEmpty()) "No phone packages" else "Package list ready"
                    error = ""
                    log(status)
                }
            },
            onError = { message ->
                mainHandler.post {
                    error = message
                    log(message)
                }
            },
        )
    }

    LaunchedEffect(pairing) {
        refreshPackages()
    }

    DisposableEffect(Unit) {
        onDispose {
            runJob?.cancel()
        }
    }

    val selectedSummary = packages.firstOrNull { it.packageId == selectedPackageId } ?: packages.firstOrNull()
    val selectedManifest = selectedSummary?.let { syncedPackages[it.packageId] }
    val phoneOwnedSession = pairing.isPhoneExport || selectedManifest?.phoneOwnedSession == true || selectedSummary?.phoneOwnedSession == true
    val fullExperimentSynced = packages.isNotEmpty() && packages.all { syncedPackages.containsKey(it.packageId) }

    fun newPhoneRunSession(runPackage: MobileRunPackage): PhoneRunSession =
        PhoneRunSession(
            packageId = runPackage.packageId,
            participantMetadata = phoneParticipantMetadata(runPackage, phoneAge, phoneHandedness, phoneGender, tactileThreshold, hapticCalibration),
            hapticMetadata = hapticCapability,
            lslContract = runPackage.lsl,
            expectedCommandToken = pairing.token,
        )

    fun startPhoneRun(runPackage: MobileRunPackage): Boolean {
        if (running || syncing || !runPackage.mobileRunnable) return false
        if (!connected && !phoneOwnedSession && !runPackage.phoneOwnedSession) return false
        val activeSession = newPhoneRunSession(runPackage)
        session = activeSession
        running = true
        activeBlockLabel = ""
        runProgress = ""
        status = "Running"
        error = ""
        uploadedArtifact = ""
        lastRunDir = ""
        val job = scope.launch {
            runCatching {
                val result = runPhonePackage(
                    context = context,
                    client = client,
                    runPackage = runPackage,
                    session = activeSession,
                    phoneOwnedSession = phoneOwnedSession || runPackage.phoneOwnedSession,
                    onStatus = { message ->
                        status = message
                        log(message)
                    },
                    onBlock = { label -> activeBlockLabel = label },
                    onProgress = { progress -> runProgress = progress },
                )
                status = "Complete"
                lastRunDir = result.optString("artifact_dir", "")
                uploadedArtifact = if (phoneOwnedSession || runPackage.phoneOwnedSession) {
                    "Saved ${result.optString("artifact_path", "")}"
                } else {
                    "Uploaded ${result.optString("artifact_path", "")}"
                }
                log("Complete")
            }.onFailure {
                error = it.message ?: "Phone run failed."
                status = "Stopped"
                log(error)
            }
            running = false
            activeBlockLabel = ""
            runProgress = ""
        }
        runJob = job
        return true
    }

    fun startFullPhoneExperiment(runPackages: List<MobileRunPackage>): Boolean {
        if (running || syncing || runPackages.isEmpty()) return false
        if (!connected && !phoneOwnedSession && runPackages.none { it.phoneOwnedSession }) return false
        running = true
        activeBlockLabel = ""
        runProgress = ""
        status = "Running full experiment"
        error = ""
        uploadedArtifact = ""
        lastRunDir = ""
        val job = scope.launch {
            runCatching {
                val artifacts = mutableListOf<String>()
                val artifactDirs = mutableListOf<String>()
                runPackages.forEachIndexed { index, runPackage ->
                    val activeSession = newPhoneRunSession(runPackage)
                    session = activeSession
                    status = "Part ${index + 1}/${runPackages.size}"
                    val result = runPhonePackage(
                        context = context,
                        client = client,
                        runPackage = runPackage,
                        session = activeSession,
                        phoneOwnedSession = phoneOwnedSession || runPackage.phoneOwnedSession,
                        onStatus = { message ->
                            status = "Part ${index + 1}/${runPackages.size} $message"
                            log(status)
                        },
                        onBlock = { label -> activeBlockLabel = label },
                        onProgress = { progress -> runProgress = progress },
                    )
                    artifacts.add(result.optString("artifact_path", ""))
                    result.optString("artifact_dir", "").takeIf { it.isNotBlank() }?.let { artifactDirs.add(it) }
                }
                status = "Full experiment complete"
                uploadedArtifact = if (phoneOwnedSession) {
                    lastRunDir = createPhoneRunBundle(context, artifactDirs).absolutePath
                    "Saved ${artifacts.size} part artifact(s)"
                } else {
                    lastRunDir = artifactDirs.lastOrNull().orEmpty()
                    "Uploaded ${artifacts.size} part artifacts"
                }
                log("Full experiment complete")
            }.onFailure {
                error = it.message ?: "Full phone experiment failed."
                status = "Stopped"
                log(error)
            }
            running = false
            activeBlockLabel = ""
            runProgress = ""
        }
        runJob = job
        return true
    }

    DisposableEffect(
        phoneRole,
        selectedPackageId,
        selectedManifest?.lsl?.commandSignalsName,
        selectedManifest?.lsl?.commandAcksName,
        selectedManifest?.partSessionId,
        selectedManifest?.sessionId,
        selectedSummary?.participantId,
    ) {
        if (phoneRole != PhoneRuntimeRole.Controller || selectedSummary == null) {
            controllerTransport = null
            onDispose { }
        } else {
            val targetSessionId = selectedManifest?.partSessionId?.ifBlank { selectedManifest.sessionId }
                ?: selectedManifest?.sessionId
                ?: pairing.sessionId
            val participantId = selectedManifest?.participantId ?: selectedSummary.participantId
            val transport = nativeControllerBridge.openControllerTransport(
                commandSignalsName = selectedManifest?.lsl?.commandSignalsName?.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME }
                    ?: PHONE_LSL_COMMAND_STREAM_NAME,
                commandAcksName = selectedManifest?.lsl?.commandAcksName?.ifBlank { PHONE_LSL_ACK_STREAM_NAME }
                    ?: PHONE_LSL_ACK_STREAM_NAME,
                sessionId = targetSessionId,
                participantId = participantId,
                controllerId = "android_controller",
            )
            controllerTransport = transport
            onDispose {
                transport.close()
                controllerTransport = null
            }
        }
    }

    LaunchedEffect(
        phoneRole,
        selectedManifest?.packageId,
        selectedManifest?.partSessionId,
        selectedManifest?.sessionId,
        running,
        syncing,
        connected,
        phoneOwnedSession,
        pairing.token,
    ) {
        val runPackage = selectedManifest
        if (phoneRole != PhoneRuntimeRole.Runner || runPackage == null || running || syncing) {
            idleRunnerCommandStatus = null
            return@LaunchedEffect
        }
        var transport: PhoneLslCommandTransport? = null
        val idleRunId = "idle-${runPackage.packageId}-${SystemClock.elapsedRealtime()}"
        try {
            while (isActive) {
                val activeTransport = transport?.takeIf { it.status.enabled } ?: run {
                    transport?.close()
                    val opened = withContext(Dispatchers.IO) {
                        nativeRunnerBridge.openCommandTransport(runPackage, idleRunId)
                    }
                    transport = opened
                    idleRunnerCommandStatus = opened.status
                    opened
                }
                if (activeTransport.status.enabled) {
                    repeat(4) {
                        val sample = withContext(Dispatchers.IO) { activeTransport.pullCommandSample(timeoutS = 0.0) } ?: return@repeat
                        val signal = runCatching { phoneCommandFromSample(sample.sample) }.getOrNull()
                        var startAfterAck = false
                        val receivedClock = sample.timestamp.takeIf { it > 0.0 } ?: activeTransport.localClock()
                        val ack = phoneCommandAckForSample(
                            sample = sample.sample,
                            runPackage = runPackage,
                            expectedToken = pairing.token,
                            receiverId = "android_phone_idle_runner",
                            receivedLslTime = receivedClock,
                            appliedLslTime = activeTransport.localClock(),
                            ackLslTime = activeTransport.localClock(),
                        ) { commandSignal ->
                            when (commandSignal.command) {
                                "start_experiment", "start_part" -> {
                                    val canStart = runPackage.mobileRunnable && !running && !syncing && (connected || phoneOwnedSession || runPackage.phoneOwnedSession)
                                    if (canStart) {
                                        startAfterAck = true
                                        PhoneLslCommandApplicationResult(
                                            status = "applied",
                                            reason = "starting_phone_run",
                                            payload = JSONObject()
                                                .put("command", commandSignal.command)
                                                .put("package_id", runPackage.packageId)
                                                .put("idle_runner_listener", true)
                                                .put("state_changed", true),
                                        )
                                    } else {
                                        PhoneLslCommandApplicationResult(
                                            status = "rejected",
                                            reason = "phone_runner_not_ready_to_start",
                                            payload = JSONObject()
                                                .put("command", commandSignal.command)
                                                .put("package_id", runPackage.packageId)
                                                .put("mobile_runnable", runPackage.mobileRunnable)
                                                .put("connected", connected)
                                                .put("phone_owned_session", phoneOwnedSession || runPackage.phoneOwnedSession)
                                                .put("running", running)
                                                .put("syncing", syncing),
                                        )
                                    }
                                }
                                "request_snapshot" -> PhoneLslCommandApplicationResult(
                                    status = "applied",
                                    reason = "idle_snapshot_recorded_in_ack_payload",
                                    payload = JSONObject()
                                        .put("command", commandSignal.command)
                                        .put("package_id", runPackage.packageId)
                                        .put("idle_runner_listener", true)
                                        .put("running", running)
                                        .put("syncing", syncing)
                                        .put("selected_package_id", runPackage.packageId)
                                        .put("synced_package_count", syncedPackages.size),
                                )
                                else -> PhoneLslCommandApplicationResult(
                                    status = "rejected",
                                    reason = "no_active_phone_run",
                                    payload = JSONObject()
                                        .put("command", commandSignal.command)
                                        .put("package_id", runPackage.packageId)
                                        .put("idle_runner_listener", true),
                                )
                            }
                        }.copy(ackLslTime = activeTransport.localClock())
                        val ackSent = withContext(Dispatchers.IO) { activeTransport.sendAck(ack) }
                        log(
                            if (ack.status == "applied") {
                                "Idle LSL ${signal?.command ?: "command"} ack=${if (ackSent) "sent" else "failed"}"
                            } else {
                                "Idle LSL rejected ${signal?.command ?: "command"}"
                            },
                        )
                        if (startAfterAck) {
                            startPhoneRun(runPackage)
                            return@LaunchedEffect
                        }
                    }
                }
                delay(if (activeTransport.status.enabled) 50L else 1000L)
            }
        } finally {
            val closingStatus = transport?.status
            transport?.close()
            if (idleRunnerCommandStatus == closingStatus) {
                idleRunnerCommandStatus = null
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusChip(if (connected) "Online" else "Offline")
            StatusChip("Session ${pairing.sessionId}")
            if (pairing.isPhoneExport) StatusChip("Phone-owned")
            StatusChip(if (phoneRole == PhoneRuntimeRole.Runner) "Runner mode" else "Controller mode")
            if (phoneRole == PhoneRuntimeRole.Controller) {
                StatusChip(if (controllerTransport?.status?.enabled == true) "LSL controller" else "Controller outbox")
            }
            if (phoneRole == PhoneRuntimeRole.Runner && idleRunnerCommandStatus?.enabled == true) {
                StatusChip("LSL idle start")
            }
            if (pairing.transport == "wifi_direct") StatusChip("Wi-Fi Direct")
            StatusChip(status)
            if (activeBlockLabel.isNotBlank()) StatusChip(activeBlockLabel)
            if (runProgress.isNotBlank()) StatusChip(runProgress)
            StatusChip(if (hapticCapability.optBoolean("has_vibrator")) "Vibrator" else "No vibrator")
            if (hapticCapability.optBoolean("has_amplitude_control")) StatusChip("Amplitude control")
        }
        if (error.isNotBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error)
        }
        if (uploadedArtifact.isNotBlank()) {
            Text(uploadedArtifact, style = MaterialTheme.typography.labelMedium)
        }
        if (lastRunDir.isNotBlank()) {
            OutlinedButton(
                onClick = {
                    runCatching {
                        val zip = exportPhoneRunZip(context, File(lastRunDir))
                        sharePhoneRunZip(context, zip)
                        uploadedArtifact = "Exported ${zip.name}"
                    }.onFailure {
                        error = it.message ?: "Export failed."
                    }
                },
                enabled = !running && !syncing,
            ) {
                Text("Export Last Session")
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = phoneRole == PhoneRuntimeRole.Runner,
                onClick = { if (!running && !syncing) phoneRole = PhoneRuntimeRole.Runner },
                enabled = !running && !syncing,
                label = { Text("Runner") },
            )
            FilterChip(
                selected = phoneRole == PhoneRuntimeRole.Controller,
                onClick = { if (!running && !syncing) phoneRole = PhoneRuntimeRole.Controller },
                enabled = !running && !syncing,
                label = { Text("Controller") },
            )
            packages.forEach { item ->
                FilterChip(
                    selected = item.packageId == selectedPackageId,
                    onClick = {
                        selectedPackageId = item.packageId
                    },
                    label = {
                        val suffix = if (syncedPackages.containsKey(item.packageId)) " synced" else ""
                        Text("${item.title.ifBlank { item.packageId }}$suffix")
                    },
                )
            }
        }
        if (phoneRole == PhoneRuntimeRole.Runner) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Phone Participant Metadata", style = MaterialTheme.typography.titleMedium)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = phoneAge,
                        onValueChange = { phoneAge = it.filter(Char::isDigit) },
                        label = { Text("Age") },
                        enabled = !running && !syncing,
                        modifier = Modifier.width(132.dp),
                    )
                    OutlinedTextField(
                        value = tactileThreshold,
                        onValueChange = { tactileThreshold = it.filter { char -> char.isDigit() || char == '.' } },
                        label = { Text("Threshold %") },
                        enabled = !running && !syncing,
                        modifier = Modifier.width(168.dp),
                    )
                }
                ChoiceRow("Handedness", phoneHandedness, listOf("right", "left", "ambidextrous", "prefer_not_to_say")) {
                    phoneHandedness = it
                }
                ChoiceRow("Gender", phoneGender, listOf("male", "female", "other", "prefer_not_to_say")) {
                    phoneGender = it
                }
                HapticCalibrationControls(
                    hapticCapability = hapticCapability,
                    calibrationSession = hapticCalibrationSession,
                    calibrationStatus = hapticCalibrationStatus,
                    enabled = !running && !syncing,
                    onStart = {
                        val started = PhoneHapticCalibrationSession.start(
                            hasVibrator = hapticCapability.optBoolean("has_vibrator", false),
                            hasAmplitudeControl = hapticCapability.optBoolean("has_amplitude_control", false),
                        )
                        hapticCalibrationSession = started
                        hapticCalibrationStatus = if (started.hasAmplitudeControl) {
                            "Pulse ${started.currentThresholdPercent}%"
                        } else {
                            "Binary pulse"
                        }
                    },
                    onPulse = { session ->
                        vibratePhone(context, session.currentAmplitude)
                    },
                    onResponse = { felt ->
                        val current = hapticCalibrationSession
                        if (current != null) {
                            val update = current.record(felt)
                            hapticCalibrationSession = update.session
                            val result = update.result
                            if (result != null) {
                                applyHapticCalibrationResult(result)
                            } else {
                                hapticCalibrationStatus = "Pulse ${update.session.currentThresholdPercent}%"
                            }
                        }
                    },
                )
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { refreshPackages() }, enabled = !running && !syncing) {
                Text("Refresh")
            }
            Button(
                onClick = {
                    val target = selectedSummary ?: return@Button
                    scope.launch {
                        syncing = true
                        status = "Syncing"
                        error = ""
                        uploadedArtifact = ""
                        runCatching {
                            val synced = syncMobilePackage(context, client, target) { message ->
                                status = message
                                log(message)
                            }
                            syncedPackages[synced.packageId] = synced
                            status = "Synced"
                            log("Synced ${synced.blocks.size} blocks")
                        }.onFailure {
                            error = it.message ?: "Sync failed."
                            log(error)
                        }
                        syncing = false
                    }
                },
                enabled = connected && selectedSummary != null && !running && !syncing,
            ) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null)
                Spacer(Modifier.padding(3.dp))
                Text(if (syncing) "Syncing" else "Sync")
            }
            if (phoneRole == PhoneRuntimeRole.Runner) {
                Button(
                    onClick = {
                        selectedManifest?.let { startPhoneRun(it) }
                    },
                    enabled = connected && selectedManifest?.mobileRunnable == true && !running && !syncing,
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Phone Run")
                }
            }
            Button(
                onClick = {
                    scope.launch {
                        syncing = true
                        status = "Syncing all"
                        error = ""
                        uploadedArtifact = ""
                        runCatching {
                            packages.forEachIndexed { index, item ->
                                val already = syncedPackages[item.packageId]
                                if (already == null) {
                                    val synced = syncMobilePackage(context, client, item) { message ->
                                        status = "Part ${index + 1}/${packages.size} $message"
                                        log(status)
                                    }
                                    syncedPackages[synced.packageId] = synced
                                }
                            }
                            status = "Full experiment synced"
                            log("Synced ${syncedPackages.size} packages")
                        }.onFailure {
                            error = it.message ?: "Sync all failed."
                            log(error)
                        }
                        syncing = false
                    }
                },
                enabled = connected && packages.isNotEmpty() && !running && !syncing,
            ) {
                Text("Sync All")
            }
            if (phoneRole == PhoneRuntimeRole.Controller) {
                val supportedCommands = selectedManifest?.lsl?.supportedCommands?.takeIf { it.isNotEmpty() }
                    ?: listOf("start_experiment", "pause", "resume", "continue_instruction", "request_snapshot")
                listOf(
                    "start_experiment" to "Start",
                    "pause" to "Pause",
                    "resume" to "Resume",
                    "continue_instruction" to "Continue",
                    "request_snapshot" to "Snapshot",
                ).filter { (command, _) -> command in supportedCommands }.forEach { (command, label) ->
                    Button(
                        onClick = {
                            scope.launch {
                                controllerSending = true
                                runCatching {
                                    withContext(Dispatchers.IO) {
                                        writePhoneControllerCommandOutbox(
                                            context = context,
                                            pairing = pairing,
                                            runPackage = selectedManifest,
                                            summary = selectedSummary,
                                            command = command,
                                            nativeBridgeStatus = nativeControllerBridge.status(),
                                            controllerTransport = controllerTransport,
                                        )
                                    }
                                }.onSuccess { result ->
                                    val sentNative = result.optBoolean("native_lsl_sent", false)
                                    val ackStatus = result.optString("ack_status", "")
                                    status = if (sentNative) "Sent $label" else "Queued $label"
                                    uploadedArtifact = buildString {
                                        append(if (sentNative) "Native LSL command sent" else "Controller outbox")
                                        if (ackStatus.isNotBlank()) append(" ack=$ackStatus")
                                        append(" ${result.optString("outbox_path", "")}")
                                    }
                                    log(if (sentNative) "Sent $command" else "Queued $command")
                                }.onFailure {
                                    error = it.message ?: "Controller command failed."
                                    log(error)
                                }
                                controllerSending = false
                            }
                        },
                        enabled = selectedSummary != null && !running && !syncing && !controllerSending,
                    ) {
                        Icon(
                            if (command == "pause") Icons.Default.Pause else Icons.AutoMirrored.Filled.Send,
                            contentDescription = null,
                        )
                        Spacer(Modifier.padding(3.dp))
                        Text(label)
                    }
                }
            }
            if (phoneRole == PhoneRuntimeRole.Runner) {
                Button(
                    onClick = {
                        val runPackages = packages.mapNotNull { syncedPackages[it.packageId] }
                        startFullPhoneExperiment(runPackages)
                    },
                    enabled = connected && fullExperimentSynced && !running && !syncing,
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.padding(3.dp))
                    Text("Start Full Experiment")
                }
                OutlinedButton(
                    onClick = {
                        runJob?.cancel()
                        running = false
                        status = "Stopped"
                    },
                    enabled = running,
                ) {
                    Text("Stop")
                }
            }
            OutlinedButton(onClick = onChooseMode, enabled = !running) {
                Text("Modes")
            }
            OutlinedButton(onClick = onUnpair, enabled = !running) {
                Text("Unpair")
            }
        }
        if (phoneRole == PhoneRuntimeRole.Runner) {
            val runSession = session
            Button(
                onClick = {
                    val recorded = runSession?.recordTap() ?: return@Button
                    status = "Tap $recorded"
                },
                enabled = running && runSession != null,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(128.dp),
            ) {
                Text("Tap Response", style = MaterialTheme.typography.headlineMedium)
            }
        }
        if (selectedSummary != null) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusChip("${selectedSummary.blockCount} blocks")
                StatusChip("${selectedSummary.trialCount} trials")
                StatusChip(formatBytes(selectedSummary.totalAssetBytes))
                StatusChip(if (selectedSummary.mobileRunnable) "Runnable" else "Not runnable")
                StatusChip(if (selectedManifest != null) "Synced" else "Not synced")
                if (selectedManifest?.lsl?.richMarkersName?.isNotBlank() == true) {
                    StatusChip("${selectedManifest.lsl.richMarkersName} mirror")
                }
                if ((selectedManifest?.buildingBlocks?.size ?: 0) > 0) {
                    StatusChip("${selectedManifest?.buildingBlocks?.size ?: 0} building blocks")
                }
            }
            selectedSummary.warnings.take(3).forEach { warning ->
                Text(warning, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        }
        if (logLines.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                logLines.take(4).forEach { line -> StatusChip(line.take(36)) }
            }
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
    onChooseMode: () -> Unit,
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
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = onChooseMode) {
                    Text("Modes")
                }
                OutlinedButton(onClick = onUnpair) {
                    Text("Unpair")
                }
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
            controls(Modifier.fillMaxSize())
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
private fun HapticCalibrationControls(
    hapticCapability: JSONObject,
    calibrationSession: PhoneHapticCalibrationSession?,
    calibrationStatus: String,
    enabled: Boolean,
    onStart: () -> Unit,
    onPulse: (PhoneHapticCalibrationSession) -> Unit,
    onResponse: (Boolean) -> Unit,
) {
    val hasVibrator = hapticCapability.optBoolean("has_vibrator", false)
    val hasAmplitudeControl = hapticCapability.optBoolean("has_amplitude_control", false)
    val current = calibrationSession
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Haptic Calibration", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedButton(
                onClick = onStart,
                enabled = enabled && hasVibrator,
            ) {
                Text(if (current == null) "Start" else "Restart")
            }
            Button(
                onClick = { current?.let(onPulse) },
                enabled = enabled && current != null && !current.isComplete,
            ) {
                Text(
                    if (current == null) {
                        "Pulse"
                    } else if (hasAmplitudeControl) {
                        "Pulse ${current.currentThresholdPercent}%"
                    } else {
                        "Pulse"
                    },
                )
            }
            OutlinedButton(
                onClick = { onResponse(false) },
                enabled = enabled && current != null && !current.isComplete,
            ) {
                Text("Not Felt")
            }
            Button(
                onClick = { onResponse(true) },
                enabled = enabled && current != null && !current.isComplete,
            ) {
                Text("Felt")
            }
        }
        if (calibrationStatus.isNotBlank()) {
            Text(calibrationStatus, style = MaterialTheme.typography.labelMedium)
        } else if (!hasVibrator) {
            Text("No vibrator", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
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

private suspend fun syncMobilePackage(
    context: Context,
    client: RunnerClient,
    summary: MobilePackageSummary,
    onStatus: (String) -> Unit,
): MobileRunPackage {
    onStatus("Fetching manifest")
    val runPackage = client.awaitMobilePackage(summary.packageId)
    require(runPackage.mobileRunnable) { "Selected package is not phone-runnable." }
    val dir = mobilePackageDir(context, runPackage.packageId)
    withContext(Dispatchers.IO) { dir.mkdirs() }
    runPackage.assets.forEachIndexed { index, asset ->
        require(asset.available) { "Missing asset ${asset.assetId}." }
        val target = mobileAssetFile(context, runPackage.packageId, asset)
        val alreadySynced = withContext(Dispatchers.IO) {
            target.isFile && target.length() == asset.sizeBytes && asset.sha256.isNotBlank() && sha256File(target) == asset.sha256
        }
        if (!alreadySynced) {
            onStatus("Downloading ${index + 1}/${runPackage.assets.size}")
            client.awaitDownloadMobileAsset(runPackage.packageId, asset.assetId, target)
        }
        if (asset.sha256.isNotBlank()) {
            val digest = withContext(Dispatchers.IO) { sha256File(target) }
            require(digest == asset.sha256) { "Checksum mismatch for ${asset.filename}." }
        }
    }
    return runPackage
}

private suspend fun runPhonePackage(
    context: Context,
    client: RunnerClient,
    runPackage: MobileRunPackage,
    session: PhoneRunSession,
    phoneOwnedSession: Boolean,
    onStatus: (String) -> Unit,
    onBlock: (String) -> Unit,
    onProgress: (String) -> Unit,
): JSONObject {
    session.recordCommand(
        command = "start_experiment",
        status = "applied",
        payload = JSONObject()
            .put("package_id", runPackage.packageId)
            .put("block_count", runPackage.blocks.size)
            .put("phone_owned_session", phoneOwnedSession),
    )
    session.addRunStart(runPackage)
    session.pollNativeCommands(runPackage)
    if (phoneOwnedSession) {
        withContext(Dispatchers.IO) { session.writeLocalArtifact(context, runPackage, complete = false) }
    } else {
        client.awaitPostMobileEvents(session.runId, session.drainPayload())
    }
    for ((blockOrderIndex, block) in runPackage.blocks.withIndex()) {
        if (session.stopAfterBlockRequested()) {
            session.addStopAfterBlockBoundary(
                lastCompletedBlock = null,
                skippedBlocks = runPackage.blocks.drop(blockOrderIndex),
                skippedTopup = true,
            )
            break
        }
        val playback = withContext(Dispatchers.IO) {
            resolvePhoneBlockPlayback(
                context = context,
                runPackage = runPackage,
                runId = session.runId,
                block = block,
            )
        }
        playback.materialization?.let { materialization ->
            session.addScheduledBlockMaterialization(materialization)
            session.recordCommand(
                command = "phone_scheduled_block_materialize",
                status = "applied",
                payload = materialization,
            )
        }
        val playbackBlock = playback.block
        onBlock(playbackBlock.label)
        onStatus("Running ${playbackBlock.index}/${runPackage.blocks.size}")
        val wavInfo = readPhonePcmWavInfo(playback.file)
        session.startBlock(playbackBlock, wavInfo)
        playBlockAudioWithAudioTrack(
            file = playback.file,
            wavInfo = wavInfo,
            cues = playbackBlock.tactileCues,
            playbackGate = session.playbackGate,
            onWhilePaused = {
                session.pollNativeCommands(runPackage)
            },
            onCue = { cue, delivery ->
                session.pollNativeCommands(runPackage)
                withContext(Dispatchers.Main) {
                    vibratePhone(context, session.vibrationAmplitude())
                    session.addCue(playbackBlock, cue, delivery)
                }
            },
            onProgress = { elapsedMs, durationMs ->
                session.pollNativeCommands(runPackage)
                withContext(Dispatchers.Main) {
                    val duration = durationMs.coerceAtLeast((playbackBlock.durationS * 1000.0).roundToLong())
                    onProgress("${formatMillisecondsShort(elapsedMs)} / ${formatMillisecondsShort(duration)}")
                }
            }
        )
        session.finishBlock(playbackBlock)
        session.pollNativeCommands(runPackage)
        if (session.stopAfterBlockRequested()) {
            session.addStopAfterBlockBoundary(
                lastCompletedBlock = playbackBlock,
                skippedBlocks = runPackage.blocks.drop(blockOrderIndex + 1),
                skippedTopup = true,
            )
            if (phoneOwnedSession) {
                withContext(Dispatchers.IO) { session.writeLocalArtifact(context, runPackage, complete = false) }
            } else {
                client.awaitPostMobileEvents(session.runId, session.drainPayload())
            }
            break
        }
        if (phoneOwnedSession) {
            withContext(Dispatchers.IO) { session.writeLocalArtifact(context, runPackage, complete = false) }
        } else {
            client.awaitPostMobileEvents(session.runId, session.drainPayload())
        }
    }
    val topupPlayed = if (session.stopAfterBlockRequested()) {
        session.addTopupSkippedByStopAfterBlock()
        onStatus("Stopped after current block")
        false
    } else {
        runPhoneTopupIfNeeded(
            context = context,
            runPackage = runPackage,
            session = session,
            onStatus = onStatus,
            onBlock = onBlock,
            onProgress = onProgress,
        )
    }
    if (topupPlayed) {
        if (phoneOwnedSession) {
            withContext(Dispatchers.IO) { session.writeLocalArtifact(context, runPackage, complete = false) }
        } else {
            client.awaitPostMobileEvents(session.runId, session.drainPayload())
        }
    }
    val completionReason = if (session.stopAfterBlockRequested()) "stopped_after_block" else "completed"
    session.addRunComplete(completionReason)
    session.recordCommand(
        command = "run_complete",
        status = "applied",
        payload = JSONObject()
            .put("package_id", runPackage.packageId)
            .put("completion_reason", completionReason),
    )
    return if (phoneOwnedSession) {
        onStatus("Saving")
        withContext(Dispatchers.IO) { session.writeLocalArtifact(context, runPackage, complete = true) }
    } else {
        onStatus("Uploading")
        client.awaitPostMobileComplete(session.runId, session.drainPayload(complete = true, runPackage = runPackage))
    }
}

private data class PhoneBlockPlayback(
    val file: File,
    val block: MobileBlock,
    val materialization: JSONObject? = null,
)

private fun resolvePhoneBlockPlayback(
    context: Context,
    runPackage: MobileRunPackage,
    runId: String,
    block: MobileBlock,
): PhoneBlockPlayback {
    val asset = runPackage.asset(block.audioAssetId)
    val audioFile = asset?.let { mobileAssetFile(context, runPackage.packageId, it) }
    if (audioFile?.isFile == true) return PhoneBlockPlayback(file = audioFile, block = block)

    val materialized = materializePhoneScheduledBlock(
        runPackage = runPackage,
        block = block,
        outputDir = File(phoneRunDir(context, runId), "materialized_blocks"),
        assetFileForId = { assetId -> runPackage.asset(assetId)?.let { mobileAssetFile(context, runPackage.packageId, it) } },
    )
    if (materialized != null) {
        return PhoneBlockPlayback(
            file = materialized.wavFile,
            block = materialized.block,
            materialization = materialized.manifest,
        )
    }

    val reason = if (asset == null) {
        "Missing audio asset ${block.audioAssetId} for ${block.label}."
    } else {
        "Synced audio file is missing for ${block.label}."
    }
    error("$reason Could not materialize the scheduled block from trial_building_block assets.")
}

private suspend fun runPhoneTopupIfNeeded(
    context: Context,
    runPackage: MobileRunPackage,
    session: PhoneRunSession,
    onStatus: (String) -> Unit,
    onBlock: (String) -> Unit,
    onProgress: (String) -> Unit,
): Boolean {
    val review = session.responseReview(runPackage)
    val materialization = withContext(Dispatchers.IO) {
        runCatching {
            materializePhoneTopupBlock(
                runPackage = runPackage,
                topupPlan = review.topupPlan,
                outputDir = phoneRunDir(context, session.runId),
                assetFileForId = { assetId -> runPackage.asset(assetId)?.let { mobileAssetFile(context, runPackage.packageId, it) } },
            )
        }
    }
    if (materialization.isFailure) {
        val reason = materialization.exceptionOrNull()?.message ?: "phone top-up materialization failed"
        val failure = failedPhoneTopupMaterialization(reason)
        session.addTopupMaterialization(failure)
        session.recordCommand("phone_topup_materialize", "rejected", reason = reason, payload = failure)
        return false
    }
    val result = materialization.getOrNull()
    if (result == null) {
        val notNeeded = notNeededPhoneTopupMaterialization()
        session.addTopupMaterialization(notNeeded)
        session.recordCommand("phone_topup_materialize", "applied", payload = notNeeded)
        return false
    }

    session.addTopupMaterialization(result.manifest)
    session.pollNativeCommands(runPackage)
    session.recordCommand(
        command = "phone_topup_materialize",
        status = "applied",
        payload = result.manifest,
    )
    onBlock(result.block.label)
    onStatus("Running phone top-up")
    val wavInfo = readPhonePcmWavInfo(result.wavFile)
    session.startBlock(result.block, wavInfo)
    playBlockAudioWithAudioTrack(
        file = result.wavFile,
        wavInfo = wavInfo,
        cues = result.block.tactileCues,
        playbackGate = session.playbackGate,
        onWhilePaused = {
            session.pollNativeCommands(runPackage)
        },
        onCue = { cue, delivery ->
            session.pollNativeCommands(runPackage)
            withContext(Dispatchers.Main) {
                vibratePhone(context, session.vibrationAmplitude())
                session.addCue(result.block, cue, delivery)
            }
        },
        onProgress = { elapsedMs, durationMs ->
            session.pollNativeCommands(runPackage)
            withContext(Dispatchers.Main) {
                onProgress("${formatMillisecondsShort(elapsedMs)} / ${formatMillisecondsShort(durationMs)}")
            }
        },
    )
    session.finishBlock(result.block)
    session.pollNativeCommands(runPackage)
    if (session.stopAfterBlockRequested()) {
        session.addStopAfterBlockBoundary(
            lastCompletedBlock = result.block,
            skippedBlocks = emptyList(),
            skippedTopup = false,
        )
    }
    session.recordCommand(
        command = "phone_topup_complete",
        status = "applied",
        payload = JSONObject()
            .put("block_id", result.block.blockId)
            .put("trial_count", result.block.trialCount)
            .put("wav_filename", result.wavFile.name),
    )
    return true
}

private class PhoneRunSession(
    val packageId: String,
    participantMetadata: JSONObject = JSONObject(),
    hapticMetadata: JSONObject = JSONObject(),
    private val lslContract: MobileLslContract = MobileLslContract.empty,
    private val expectedCommandToken: String = "",
    private val nativeLslBridge: PhoneNativeLslBridge = PhoneNativeLslBridgeFactory.create(),
) {
    val runId: String = "phone-${System.currentTimeMillis()}"
    val playbackGate = PhoneAudioPlaybackGate()
    private val events = mutableListOf<JSONObject>()
    private val pendingEvents = mutableListOf<JSONObject>()
    private val lslMarkers = mutableListOf<JSONObject>()
    private val commandDiary = mutableListOf<JSONObject>()
    private val participantMetadata = JSONObject(participantMetadata.toString())
    private val hapticMetadata = JSONObject(hapticMetadata.toString())
    private var activeBlock: MobileBlock? = null
    private var blockStartElapsedMs: Long = 0L
    private var blockPausedAccumulatedMs: Long = 0L
    private var pauseStartedElapsedMs: Long = 0L
    private val startedUnixMs: Long = System.currentTimeMillis()
    private var completedUnixMs: Long = 0L
    private var tapCount: Int = 0
    private var validTapCount: Int = 0
    private var latestLslRuntimeStatus: JSONObject = JSONObject()
    private var markerTransport: PhoneLslMarkerTransport? = null
    private var commandTransport: PhoneLslCommandTransport? = null
    private var lastCommandTransportResolveAttemptMs: Long = 0L
    private var nativeLslClockOffsetS: Double = 0.0
    private var nativeLslPushedCount: Int = 0
    private var nativeLslFailedCount: Int = 0
    private var nativeLslCommandReceivedCount: Int = 0
    private var nativeLslCommandAckCount: Int = 0
    private var nativeLslCommandAckFailedCount: Int = 0
    private var nativeLslCommandRejectedCount: Int = 0
    private var phonePauseCount: Int = 0
    private var phoneResumeCount: Int = 0
    private var stopAfterBlockRequested: Boolean = false
    private var phoneStopAfterBlockRequestCount: Int = 0
    private var stopAfterBlockBoundaryRecorded: Boolean = false
    private var phoneTopupSkippedByStopAfterBlock: Boolean = false
    private var completionReason: String = "in_progress"

    @Synchronized
    fun addRunStart(runPackage: MobileRunPackage) {
        markerTransport = nativeLslBridge.openMarkerTransport(runPackage, runId)
        commandTransport = nativeLslBridge.openCommandTransport(runPackage, runId)
        lastCommandTransportResolveAttemptMs = SystemClock.elapsedRealtime()
        nativeLslClockOffsetS = markerTransport?.let { transport ->
            transport.localClock() - (SystemClock.elapsedRealtime() / 1000.0)
        } ?: 0.0
        latestLslRuntimeStatus = phoneLslRuntimeStatus(
            runPackage = runPackage,
            runId = runId,
            nativeBridgeStatus = nativeLslBridge.status(),
            markerTransportStatus = markerTransport?.status,
            commandTransportStatus = commandTransport?.status,
        )
        addEventLocked(
            "session_metadata",
            JSONObject()
                .put("participant_metadata", JSONObject(participantMetadata.toString()))
                .put("haptic", JSONObject(hapticMetadata.toString()))
                .put(
                    "package",
                    JSONObject()
                        .put("package_id", runPackage.packageId)
                        .put("participant_id", runPackage.participantId)
                        .put("session_id", runPackage.sessionId)
                        .put("session_group_id", runPackage.sessionGroupId)
                        .put("part_session_id", runPackage.partSessionId)
                        .put("part_number", runPackage.partNumber)
                        .put("title", runPackage.title)
                        .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
                        .put("block_count", runPackage.blocks.size)
                        .put("asset_count", runPackage.assets.size)
                        .put("building_block_count", runPackage.buildingBlocks.size)
                        .put("schedule_hash", runPackage.reconstruction.scheduleHash),
                )
                .put(
                    "lsl",
                    JSONObject()
                        .put("schema", lslContract.schema)
                        .put("runtime_authority", lslContract.runtimeAuthority.ifBlank { "android_phone" })
                        .put("privacy_default", lslContract.privacyDefault)
                        .put("rich_markers_name", lslContract.richMarkersName.ifBlank { "PPSMarkersV2" })
                        .put("numeric_triggers_name", lslContract.numericTriggersName.ifBlank { "PPSTriggerCodes" })
                        .put("command_signals_name", lslContract.commandSignalsName.ifBlank { "PPSCommandSignalsV1" })
                        .put("command_acks_name", lslContract.commandAcksName.ifBlank { "PPSCommandAcksV1" })
                        .put("native_android_lsl_required", lslContract.nativeAndroidLslRequired)
                        .put("current_android_source_behavior", lslContract.currentAndroidSourceBehavior.ifBlank { "local_lsl_marker_mirror" }),
                )
                .put("lsl_runtime_status", JSONObject(latestLslRuntimeStatus.toString())),
        )
        addEventLocked(
            "run_start",
            JSONObject()
                .put("participant_id", runPackage.participantId)
                .put("session_id", runPackage.sessionId)
                .put("block_count", runPackage.blocks.size),
        )
    }

    @Synchronized
    fun startBlock(block: MobileBlock, wavInfo: PhonePcmWavInfo? = null) {
        activeBlock = block
        blockStartElapsedMs = SystemClock.elapsedRealtime()
        blockPausedAccumulatedMs = 0L
        pauseStartedElapsedMs = if (playbackGate.isPaused()) blockStartElapsedMs else 0L
        val payload = JSONObject()
            .put("block_id", block.blockId)
            .put("block_index", block.index)
            .put("block_label", block.label)
            .put("duration_s", block.durationS)
            .put("trial_count", block.trialCount)
            .put("audio_timing_strategy", "audiotrack_pcm_wav_playback_head")
        if (wavInfo != null) {
            payload
                .put("audio_sample_rate_hz", wavInfo.sampleRateHz)
                .put("audio_channel_count", wavInfo.channelCount)
                .put("audio_bits_per_sample", wavInfo.bitsPerSample)
                .put("audio_encoding", wavInfo.encodingLabel)
                .put("audio_frame_count", wavInfo.frameCount)
                .put("audio_duration_ms", wavInfo.durationMs)
                .put("audio_data_size_bytes", wavInfo.dataSizeBytes)
        }
        addEventLocked("block_start", payload)
    }

    @Synchronized
    fun addCue(block: MobileBlock, cue: MobileCue, delivery: PhoneAudioCueDelivery? = null) {
        val payload = JSONObject()
            .put("block_id", block.blockId)
            .put("block_index", block.index)
            .put("cue_id", cue.cueId)
            .put("trial_number", cue.trialNumber)
            .put("trial_uid", cue.trialUid)
            .put("scheduled_block_time_ms", (cue.timeS * 1000.0).roundToLong())
            .put("actual_block_time_ms", currentBlockElapsedMs())
            .put("soa_ms", cue.soaMs)
            .put("row_label", cue.rowLabel)
            .put("noise_type", cue.noiseType)
        if (delivery != null) {
            payload
                .put("audio_scheduler", "audiotrack_playback_head")
                .put("scheduled_audio_frame", delivery.scheduledAudioFrame)
                .put("audio_playback_head_frame", delivery.playbackHeadFrame)
                .put("audio_delivery_elapsed_realtime_ms", delivery.deliveryElapsedRealtimeMs)
                .put("audio_cue_jitter_frames", delivery.jitterFrames)
                .put("audio_cue_jitter_ms", delivery.jitterMs)
        }
        addEventLocked("vibration_cue", payload)
    }

    @Synchronized
    fun finishBlock(block: MobileBlock) {
        addEventLocked(
            "block_complete",
            JSONObject()
                .put("block_id", block.blockId)
                .put("block_index", block.index)
                .put("block_label", block.label)
                .put("actual_block_duration_ms", currentBlockElapsedMs()),
        )
        activeBlock = null
        blockPausedAccumulatedMs = 0L
        pauseStartedElapsedMs = 0L
    }

    @Synchronized
    fun stopAfterBlockRequested(): Boolean = stopAfterBlockRequested

    @Synchronized
    fun addStopAfterBlockBoundary(
        lastCompletedBlock: MobileBlock?,
        skippedBlocks: List<MobileBlock>,
        skippedTopup: Boolean,
    ) {
        if (!stopAfterBlockRequested || stopAfterBlockBoundaryRecorded) return
        stopAfterBlockBoundaryRecorded = true
        addEventLocked(
            "phone_stop_after_block_boundary",
            JSONObject()
                .put("last_completed_block_id", lastCompletedBlock?.blockId.orEmpty())
                .put("last_completed_block_index", lastCompletedBlock?.index ?: JSONObject.NULL)
                .put("last_completed_block_label", lastCompletedBlock?.label.orEmpty())
                .put("skipped_block_count", skippedBlocks.size)
                .put(
                    "skipped_blocks",
                    JSONArray().also { array ->
                        skippedBlocks.forEach { block ->
                            array.put(
                                JSONObject()
                                    .put("block_id", block.blockId)
                                    .put("block_index", block.index)
                                    .put("block_label", block.label)
                                    .put("trial_count", block.trialCount),
                            )
                        }
                    },
                )
                .put("skipped_phone_topup", skippedTopup),
        )
    }

    @Synchronized
    fun addTopupSkippedByStopAfterBlock() {
        if (phoneTopupSkippedByStopAfterBlock) return
        phoneTopupSkippedByStopAfterBlock = true
        addTopupMaterialization(
            JSONObject()
                .put("schema", "pps-android-phone-topup-materialization.v1")
                .put("status", "skipped")
                .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
                .put("reason", "stop_after_block_requested"),
        )
    }

    @Synchronized
    fun responseReview(runPackage: MobileRunPackage): PhoneResponseReview =
        buildPhoneResponseReview(runPackage, events.map { JSONObject(it.toString()) })

    @Synchronized
    fun addTopupMaterialization(materialization: JSONObject) {
        addEventLocked("phone_topup_materialization", JSONObject(materialization.toString()))
    }

    @Synchronized
    fun addScheduledBlockMaterialization(materialization: JSONObject) {
        addEventLocked("phone_scheduled_block_materialization", JSONObject(materialization.toString()))
    }

    @Synchronized
    fun addRunComplete(reason: String = "completed") {
        completionReason = reason
        completedUnixMs = System.currentTimeMillis()
        addEventLocked(
            "run_complete",
            JSONObject()
                .put("total_events", events.size)
                .put("completion_reason", reason),
        )
    }

    @Synchronized
    fun pollNativeCommands(runPackage: MobileRunPackage, maxCommands: Int = 4) {
        val transport = commandTransportForPollingLocked(runPackage) ?: return
        repeat(maxCommands.coerceAtLeast(1)) {
            val sample = transport.pullCommandSample(timeoutS = 0.0) ?: return
            nativeLslCommandReceivedCount += 1
            val parsedSignal = runCatching { phoneCommandFromSample(sample.sample) }.getOrNull()
            val receivedClock = sample.timestamp.takeIf { it > 0.0 } ?: transport.localClock()
            val ack = phoneCommandAckForSample(
                sample = sample.sample,
                runPackage = runPackage,
                expectedToken = expectedCommandToken,
                receiverId = "android_phone",
                receivedLslTime = receivedClock,
                appliedLslTime = transport.localClock(),
                ackLslTime = transport.localClock(),
            ) { signal ->
                applyNativePhoneCommandLocked(signal)
            }.copy(ackLslTime = transport.localClock())
            val ackSent = transport.sendAck(ack)
            if (ackSent) {
                nativeLslCommandAckCount += 1
            } else {
                nativeLslCommandAckFailedCount += 1
            }
            if (ack.status != "applied") {
                nativeLslCommandRejectedCount += 1
            }
            recordNativeCommandAckLocked(parsedSignal, ack, ackSent)
        }
    }

    private fun commandTransportForPollingLocked(runPackage: MobileRunPackage): PhoneLslCommandTransport? {
        val existing = commandTransport
        if (existing?.status?.enabled == true) return existing
        if (!nativeLslBridge.status().available) return existing
        val now = SystemClock.elapsedRealtime()
        if (now - lastCommandTransportResolveAttemptMs < 1000L) return existing
        lastCommandTransportResolveAttemptMs = now
        existing?.close()
        val reopened = nativeLslBridge.openCommandTransport(runPackage, runId)
        commandTransport = reopened
        latestLslRuntimeStatus = phoneLslRuntimeStatus(
            runPackage = runPackage,
            runId = runId,
            nativeBridgeStatus = nativeLslBridge.status(),
            markerTransportStatus = markerTransport?.status,
            commandTransportStatus = reopened.status,
        )
        return reopened.takeIf { it.status.enabled }
    }

    @Synchronized
    fun recordCommand(command: String, status: String, reason: String = "", payload: JSONObject = JSONObject()) {
        val row = JSONObject()
            .put("schema", "pps-android-command-diary.v1")
            .put("command_id", "phone-${commandDiary.size + 1}")
            .put("command_source", "phone_ui_or_runtime")
            .put("command", command)
            .put("status", status)
            .put("reason", reason)
            .put("payload", JSONObject(payload.toString()))
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("phone_unix_ms", System.currentTimeMillis())
            .put("phone_elapsed_realtime_ms", SystemClock.elapsedRealtime())
        commandDiary.add(row)
        addEventLocked(
            "operator_command",
            JSONObject()
                .put("command_id", row.optString("command_id"))
                .put("command", command)
                .put("status", status)
                .put("reason", reason)
                .put("payload", JSONObject(payload.toString())),
        )
    }

    private fun applyNativePhoneCommandLocked(signal: PhoneLslCommandSignal): PhoneLslCommandApplicationResult =
        when (signal.command) {
            "request_snapshot" -> PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "snapshot_recorded_in_ack_payload",
                payload = nativeCommandStatePayloadLocked(signal.command),
            )
            "operator_note" -> PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "operator_note_recorded",
                payload = nativeCommandStatePayloadLocked(signal.command)
                    .put("note", signal.payload.optString("note")),
            )
            "start_experiment", "start_part" -> PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "already_running_on_phone",
                payload = nativeCommandStatePayloadLocked(signal.command),
            )
            "continue_instruction" -> PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "no_instruction_gate_active_in_phone_runtime",
                payload = nativeCommandStatePayloadLocked(signal.command),
            )
            "pause" -> applyPhonePauseLocked(signal.command)
            "resume" -> applyPhoneResumeLocked(signal.command)
            "stop_after_block" -> applyPhoneStopAfterBlockLocked(signal)
            else -> PhoneLslCommandApplicationResult(
                status = "rejected",
                reason = "unsupported_phone_native_command",
                payload = nativeCommandStatePayloadLocked(signal.command),
            )
        }

    private fun applyPhonePauseLocked(command: String): PhoneLslCommandApplicationResult {
        val block = activeBlock
        if (block == null) {
            return PhoneLslCommandApplicationResult(
                status = "rejected",
                reason = "no_active_phone_block_to_pause",
                payload = nativeCommandStatePayloadLocked(command),
            )
        }
        val changed = playbackGate.pause()
        if (changed) {
            pauseStartedElapsedMs = SystemClock.elapsedRealtime()
            phonePauseCount += 1
            addEventLocked(
                "phone_playback_pause",
                JSONObject()
                    .put("block_id", block.blockId)
                    .put("block_index", block.index)
                    .put("block_label", block.label)
                    .put("block_elapsed_ms", currentBlockElapsedMs()),
            )
        }
        return PhoneLslCommandApplicationResult(
            status = "applied",
            reason = if (changed) "phone_playback_paused" else "already_paused",
            payload = nativeCommandStatePayloadLocked(command)
                .put("state_changed", changed),
        )
    }

    private fun applyPhoneResumeLocked(command: String): PhoneLslCommandApplicationResult {
        if (!playbackGate.isPaused()) {
            return PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "already_running",
                payload = nativeCommandStatePayloadLocked(command)
                    .put("state_changed", false),
            )
        }
        val now = SystemClock.elapsedRealtime()
        if (pauseStartedElapsedMs > 0L) {
            blockPausedAccumulatedMs += (now - pauseStartedElapsedMs).coerceAtLeast(0L)
        }
        pauseStartedElapsedMs = 0L
        val changed = playbackGate.resume()
        phoneResumeCount += 1
        addEventLocked(
            "phone_playback_resume",
            JSONObject()
                .put("block_id", activeBlock?.blockId.orEmpty())
                .put("block_index", activeBlock?.index ?: JSONObject.NULL)
                .put("block_label", activeBlock?.label.orEmpty())
                .put("block_elapsed_ms", currentBlockElapsedMs())
                .put("paused_accumulated_ms", blockPausedAccumulatedMs),
        )
        return PhoneLslCommandApplicationResult(
            status = "applied",
            reason = if (changed) "phone_playback_resumed" else "already_running",
            payload = nativeCommandStatePayloadLocked(command)
                .put("state_changed", changed),
        )
    }

    private fun applyPhoneStopAfterBlockLocked(signal: PhoneLslCommandSignal): PhoneLslCommandApplicationResult {
        val changed = !stopAfterBlockRequested
        if (changed) {
            stopAfterBlockRequested = true
            phoneStopAfterBlockRequestCount += 1
            val block = activeBlock
            addEventLocked(
                "phone_stop_after_block_request",
                JSONObject()
                    .put("command_id", signal.commandId)
                    .put("sender_id", signal.senderId)
                    .put("active_block_id", block?.blockId.orEmpty())
                    .put("active_block_index", block?.index ?: JSONObject.NULL)
                    .put("active_block_label", block?.label.orEmpty())
                    .put("active_block_elapsed_ms", currentBlockElapsedMs())
                    .put("boundary_policy", if (block == null) "stop_before_next_block" else "finish_active_block_then_stop"),
            )
        }
        val reason = when {
            !changed -> "stop_after_block_already_requested"
            activeBlock == null -> "will_stop_before_next_block"
            else -> "will_stop_after_current_block"
        }
        return PhoneLslCommandApplicationResult(
            status = "applied",
            reason = reason,
            payload = nativeCommandStatePayloadLocked(signal.command)
                .put("state_changed", changed)
                .put("boundary_policy", if (activeBlock == null) "stop_before_next_block" else "finish_active_block_then_stop"),
        )
    }

    private fun nativeCommandStatePayloadLocked(command: String): JSONObject =
        JSONObject()
            .put("command", command)
            .put("run_id", runId)
            .put("package_id", packageId)
            .put("active_block_id", activeBlock?.blockId.orEmpty())
            .put("active_block_index", activeBlock?.index ?: JSONObject.NULL)
            .put("active_block_elapsed_ms", currentBlockElapsedMs())
            .put("event_count", events.size)
            .put("tap_count", tapCount)
            .put("valid_tap_count", validTapCount)
            .put("paused", playbackGate.isPaused())
            .put("phone_pause_count", phonePauseCount)
            .put("phone_resume_count", phoneResumeCount)
            .put("stop_after_block_requested", stopAfterBlockRequested)
            .put("phone_stop_after_block_request_count", phoneStopAfterBlockRequestCount)
            .put("stop_after_block_boundary_recorded", stopAfterBlockBoundaryRecorded)
            .put("phone_topup_skipped_by_stop_after_block", phoneTopupSkippedByStopAfterBlock)
            .put("block_paused_accumulated_ms", blockPausedAccumulatedMs + currentLivePauseDurationMs())
            .put("phone_unix_ms", System.currentTimeMillis())
            .put("phone_elapsed_realtime_ms", SystemClock.elapsedRealtime())

    private fun recordNativeCommandAckLocked(
        signal: PhoneLslCommandSignal?,
        ack: PhoneLslCommandAck,
        ackSent: Boolean,
    ) {
        val ackSample = phoneAckToSample(ack)
        val command = signal?.command ?: "invalid_lsl_command"
        val commandId = ack.commandId.ifBlank { signal?.commandId ?: "native-${commandDiary.size + 1}" }
        val row = JSONObject()
            .put("schema", "pps-android-command-diary.v1")
            .put("command_id", commandId)
            .put("command_source", "native_lsl")
            .put("sender_id", signal?.senderId.orEmpty())
            .put("session_id", ack.sessionId)
            .put("command", command)
            .put("status", ack.status)
            .put("reason", ack.reason)
            .put("payload", JSONObject(ack.payload.toString()))
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("received_lsl_time", ack.receivedLslTime)
            .put("applied_lsl_time", ack.appliedLslTime)
            .put("ack_lsl_time", ack.ackLslTime)
            .put("ack_sent", ackSent)
            .put("ack_channels", jsonStringArray(PHONE_LSL_ACK_CHANNELS))
            .put("ack_sample", jsonStringArray(ackSample))
            .put("phone_unix_ms", System.currentTimeMillis())
            .put("phone_elapsed_realtime_ms", SystemClock.elapsedRealtime())
        commandDiary.add(row)
        addEventLocked(
            "operator_command",
            JSONObject()
                .put("command_id", commandId)
                .put("command_source", "native_lsl")
                .put("sender_id", signal?.senderId.orEmpty())
                .put("command", command)
                .put("status", ack.status)
                .put("reason", ack.reason)
                .put("ack_sent", ackSent)
                .put("payload", JSONObject(ack.payload.toString())),
        )
    }

    fun vibrationAmplitude(): Int {
        if (!hapticMetadata.optBoolean("has_amplitude_control", false)) return VibrationEffect.DEFAULT_AMPLITUDE
        val threshold = participantMetadata.optDouble("tactile_threshold_percent", Double.NaN)
            .takeIf { it.isFinite() && it > 0.0 }
            ?: hapticMetadata.optDouble("recommended_threshold_percent", Double.NaN)
        if (threshold.isNaN() || threshold.isInfinite() || threshold <= 0.0) return VibrationEffect.DEFAULT_AMPLITUDE
        return phoneHapticAmplitudeFromPercent(threshold, hasAmplitudeControl = true)
    }

    @Synchronized
    fun recordTap(): Int {
        tapCount += 1
        val block = activeBlock
        val elapsedMs = currentBlockElapsedMs()
        val priorCue = block?.tactileCues
            ?.filter { elapsedMs >= (it.timeS * 1000.0).roundToLong() }
            ?.minByOrNull { cue -> abs(elapsedMs - (cue.timeS * 1000.0).roundToLong()) }
        val cueMs = priorCue?.let { (it.timeS * 1000.0).roundToLong() }
        val rtMs = cueMs?.let { elapsedMs - it }
        val valid = rtMs != null && rtMs in PHONE_RESPONSE_MIN_RT_MS..PHONE_RESPONSE_MAX_RT_MS
        if (valid) validTapCount += 1
        val payload = JSONObject()
            .put("tap_index", tapCount)
            .put("block_elapsed_ms", elapsedMs)
            .put("response_status", if (valid) "tactile_response" else "off_cue")
        if (block != null) {
            payload
                .put("block_id", block.blockId)
                .put("block_index", block.index)
                .put("block_label", block.label)
        }
        if (priorCue != null) {
            payload
                .put("cue_id", priorCue.cueId)
                .put("trial_uid", priorCue.trialUid)
                .put("trial_number", priorCue.trialNumber)
                .put("rt_ms", rtMs)
        }
        addEventLocked("tap", payload)
        return tapCount
    }

    @Synchronized
    fun drainPayload(complete: Boolean = false, runPackage: MobileRunPackage? = null): JSONObject {
        val eventsArray = JSONArray()
        pendingEvents.forEach { eventsArray.put(JSONObject(it.toString())) }
        pendingEvents.clear()
        val payload = JSONObject()
            .put("schema", if (complete) "pps-mobile-run-complete.v1" else "pps-mobile-run-events.v1")
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("completed", complete)
            .put("events", eventsArray)
            .put("participant_metadata", JSONObject(participantMetadata.toString()))
            .put("haptic", JSONObject(hapticMetadata.toString()))
            .put("lsl_runtime_status", JSONObject(latestLslRuntimeStatus.toString()))
            .put("lsl_marker_mirror", JSONArray().also { array -> lslMarkers.forEach { array.put(JSONObject(it.toString())) } })
            .put("command_diary", JSONArray().also { array -> commandDiary.forEach { array.put(JSONObject(it.toString())) } })
            .put("summary", summaryLocked())
        if (complete && runPackage != null) {
            val responseReview = buildPhoneResponseReview(runPackage, events.map { JSONObject(it.toString()) })
            payload
                .put("phone_response_summary", JSONObject(responseReview.summary.toString()))
                .put("phone_response_ledger", JSONArray().also { array ->
                    responseReview.ledgerRows.forEach { array.put(JSONObject(it.toString())) }
                })
                .put("phone_topup_plan", JSONObject(responseReview.topupPlan.toString()))
                .put("phone_topup_materialization", latestTopupMaterializationLocked())
        }
        if (complete) closeNativeLslTransportLocked()
        return payload
    }

    @Synchronized
    fun writeLocalArtifact(context: Context, runPackage: MobileRunPackage, complete: Boolean): JSONObject {
        val dir = phoneRunDir(context, runId)
        dir.mkdirs()
        val eventsArray = JSONArray()
        events.forEach { eventsArray.put(JSONObject(it.toString())) }
        val packageManifestText = phoneRunPackageManifestText(runPackage)
        val packageManifestSha256 = sha256Text(packageManifestText)
        val packageManifestFile = File(dir, "run_package_manifest.json")
        val reconstructionFile = File(dir, "reconstruction_contract.json")
        val lslRuntimeStatus = phoneLslRuntimeStatus(
            runPackage = runPackage,
            runId = runId,
            nativeBridgeStatus = nativeLslBridge.status(),
            markerTransportStatus = markerTransport?.status,
            commandTransportStatus = commandTransport?.status,
        )
        latestLslRuntimeStatus = JSONObject(lslRuntimeStatus.toString())
        val lslRuntimeStatusFile = File(dir, "lsl_runtime_status.json")
        val responseReview = buildPhoneResponseReview(runPackage, events)
        val responseLedgerFile = File(dir, "phone_response_ledger.csv")
        val topupPlanFile = File(dir, "phone_topup_plan.json")
        val topupMaterializationFile = File(dir, "phone_topup_materialization.json")
        val artifactFile = File(dir, if (complete) "completion.json" else "latest_events.json")
        val dataExportArtifactFile = File(dir, "phone_owned_data_export.json")
        val topupMaterialization = if (complete && phoneTopupSkippedByStopAfterBlock) {
            JSONObject()
                .put("schema", "pps-android-phone-topup-materialization.v1")
                .put("status", "skipped")
                .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
                .put("reason", "stop_after_block_requested")
        } else if (complete) {
            runCatching {
                materializePhoneTopupBlock(
                    runPackage = runPackage,
                    topupPlan = responseReview.topupPlan,
                    outputDir = dir,
                    assetFileForId = { assetId -> runPackage.asset(assetId)?.let { mobileAssetFile(context, runPackage.packageId, it) } },
                )?.manifest ?: notNeededPhoneTopupMaterialization()
            }.getOrElse { error -> failedPhoneTopupMaterialization(error.message ?: error::class.java.simpleName) }
        } else {
            JSONObject()
                .put("schema", "pps-android-phone-topup-materialization.v1")
                .put("status", "not_evaluated")
                .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
                .put("reason", "session_in_progress")
        }
        val summary = summaryLocked()
        val catalogEntry = buildPhoneRunCatalogEntry(
            runPackage = runPackage,
            runId = runId,
            runDir = dir,
            artifactFile = artifactFile,
            complete = complete,
            participantMetadata = participantMetadata,
            lslRuntimeStatus = lslRuntimeStatus,
            summary = summary,
        )
        val payload = JSONObject()
            .put("schema", if (complete) "pps-mobile-run-complete.v1" else "pps-mobile-run-events.v1")
            .put("status", if (complete) "complete" else "in_progress")
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("completed", complete)
            .put("phone_owned_session", true)
            .put("participant_metadata", JSONObject(participantMetadata.toString()))
            .put("haptic", JSONObject(hapticMetadata.toString()))
            .put(
                "package",
                JSONObject()
                    .put("participant_id", runPackage.participantId)
                    .put("session_id", runPackage.sessionId)
                    .put("title", runPackage.title)
                    .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
                    .put("block_count", runPackage.blocks.size),
            )
            .put(
                "package_manifest",
                JSONObject()
                    .put("filename", packageManifestFile.name)
                    .put("sha256", packageManifestSha256),
            )
            .put(
                "reconstruction_artifact",
                JSONObject()
                    .put("filename", reconstructionFile.name)
                    .put("schema", "pps-mobile-phone-run-reconstruction.v1"),
            )
            .put(
                "lsl_runtime_status_artifact",
                JSONObject()
                    .put("filename", lslRuntimeStatusFile.name)
                    .put("schema", PHONE_LSL_RUNTIME_STATUS_SCHEMA),
            )
            .put(
                "phone_run_catalog_artifact",
                JSONObject()
                    .put("filename", "phone_run_catalog_entry.json")
                    .put("schema", PHONE_RUN_CATALOG_ENTRY_SCHEMA),
            )
            .put(
                "phone_owned_data_export_artifact",
                JSONObject()
                    .put("filename", dataExportArtifactFile.name)
                    .put("schema", PHONE_OWNED_DATA_EXPORT_SCHEMA)
                    .put("written_when_complete", true),
            )
            .put("lsl_runtime_status", JSONObject(lslRuntimeStatus.toString()))
            .put("events", eventsArray)
            .put("lsl_marker_mirror", JSONArray().also { array -> lslMarkers.forEach { array.put(JSONObject(it.toString())) } })
            .put("command_diary", JSONArray().also { array -> commandDiary.forEach { array.put(JSONObject(it.toString())) } })
            .put("phone_response_summary", JSONObject(responseReview.summary.toString()))
            .put("phone_response_ledger", JSONArray().also { array -> responseReview.ledgerRows.forEach { array.put(JSONObject(it.toString())) } })
            .put("phone_topup_plan", JSONObject(responseReview.topupPlan.toString()))
            .put("phone_topup_materialization", JSONObject(topupMaterialization.toString()))
            .put("phone_run_catalog_entry", JSONObject(catalogEntry.toString()))
            .put("summary", JSONObject(summary.toString()))
        packageManifestFile.writeText(packageManifestText, Charsets.UTF_8)
        reconstructionFile.writeText(phoneRunReconstructionArtifact(runPackage, packageManifestSha256).toString(2), Charsets.UTF_8)
        lslRuntimeStatusFile.writeText(lslRuntimeStatus.toString(2), Charsets.UTF_8)
        artifactFile.writeText(payload.toString(2), Charsets.UTF_8)
        writePhoneEventsCsv(File(dir, "events.csv"), events)
        writePhoneEventsCsv(File(dir, "lsl_marker_mirror.csv"), lslMarkers)
        writePhoneTriggerCodesCsv(File(dir, "trigger_codes.csv"), lslMarkers)
        writePhoneEventsCsv(responseLedgerFile, responseReview.ledgerRows)
        topupPlanFile.writeText(responseReview.topupPlan.toString(2), Charsets.UTF_8)
        topupMaterializationFile.writeText(topupMaterialization.toString(2), Charsets.UTF_8)
        writeCommandDiaryJsonl(File(dir, "command_diary.jsonl"), commandDiary)
        File(dir, "participant_metadata.json").writeText(participantMetadata.toString(2), Charsets.UTF_8)
        File(dir, "haptic_capability.json").writeText(hapticMetadata.toString(2), Charsets.UTF_8)
        val catalogWrite = writePhoneRunCatalog(context.filesDir, dir, catalogEntry)
        val dataExport = if (complete) {
            writePhoneOwnedDataExport(
                filesDir = context.filesDir,
                runPackage = runPackage,
                runDir = dir,
                catalogEntry = catalogEntry,
                responseLedgerRows = responseReview.ledgerRows,
            )
        } else {
            null
        }
        if (complete) closeNativeLslTransportLocked()
        return JSONObject()
            .put("schema", if (complete) "pps-mobile-run-complete.v1" else "pps-mobile-run-events.v1")
            .put("status", if (complete) "saved" else "saved_partial")
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("event_count", events.size)
            .put("artifact_path", artifactFile.absolutePath)
            .put("artifact_dir", dir.absolutePath)
            .put("package_manifest_path", packageManifestFile.absolutePath)
            .put("reconstruction_artifact_path", reconstructionFile.absolutePath)
            .put("lsl_runtime_status_path", lslRuntimeStatusFile.absolutePath)
            .put("response_ledger_path", responseLedgerFile.absolutePath)
            .put("topup_plan_path", topupPlanFile.absolutePath)
            .put("topup_materialization_path", topupMaterializationFile.absolutePath)
            .put("catalog_entry_path", catalogWrite.optString("entry_path"))
            .put("catalog_participant_runs_path", catalogWrite.optString("participant_runs_path"))
            .put("catalog_index_path", catalogWrite.optString("index_path"))
            .put("phone_owned_data_export_path", dataExport?.optString("artifact_path").orEmpty())
            .put("phone_owned_data_min_participant_csv", dataExport?.optString("data_min_participant_csv").orEmpty())
            .put("phone_owned_data_min_master_csv", dataExport?.optString("data_min_master_successful_participants_csv").orEmpty())
            .put("phone_owned_data_max_run_dir", dataExport?.optString("data_max_run_dir").orEmpty())
    }

    private fun currentBlockElapsedMs(): Long =
        if (blockStartElapsedMs <= 0L) {
            0L
        } else {
            (SystemClock.elapsedRealtime() - blockStartElapsedMs - blockPausedAccumulatedMs - currentLivePauseDurationMs())
                .coerceAtLeast(0L)
        }

    private fun currentLivePauseDurationMs(): Long =
        if (playbackGate.isPaused() && pauseStartedElapsedMs > 0L) {
            (SystemClock.elapsedRealtime() - pauseStartedElapsedMs).coerceAtLeast(0L)
        } else {
            0L
        }

    private fun latestTopupMaterializationLocked(): JSONObject {
        val event = events.asReversed().firstOrNull { it.optString("type") == "phone_topup_materialization" }
        if (event != null) {
            return JSONObject(event.toString()).also { materialization ->
                listOf(
                    "type",
                    "event_id",
                    "package_id",
                    "run_id",
                    "phone_unix_ms",
                    "phone_elapsed_realtime_ms",
                ).forEach { materialization.remove(it) }
            }
        }
        if (phoneTopupSkippedByStopAfterBlock) {
            return JSONObject()
                .put("schema", "pps-android-phone-topup-materialization.v1")
                .put("status", "skipped")
                .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
                .put("reason", "stop_after_block_requested")
        }
        return notNeededPhoneTopupMaterialization()
    }

    private fun addEventLocked(type: String, payload: JSONObject) {
        val eventId = events.size + 1
        val event = JSONObject(payload.toString())
            .put("type", type)
            .put("event_id", eventId)
            .put("package_id", packageId)
            .put("run_id", runId)
            .put("phone_unix_ms", System.currentTimeMillis())
            .put("phone_elapsed_realtime_ms", SystemClock.elapsedRealtime())
        events.add(event)
        pendingEvents.add(event)
        val marker = markerFromEvent(event)
        lslMarkers.add(marker)
        pushNativeLslMarkerLocked(marker)
    }

    private fun pushNativeLslMarkerLocked(marker: JSONObject) {
        val transport = markerTransport ?: return
        val timestamp = marker.optDouble("phone_elapsed_realtime_ms", Double.NaN)
            .takeIf { it.isFinite() }
            ?.let { (it / 1000.0) + nativeLslClockOffsetS }
            ?: transport.localClock()
        if (transport.pushMarker(marker, timestamp)) {
            nativeLslPushedCount += 1
        } else {
            nativeLslFailedCount += 1
        }
    }

    private fun closeNativeLslTransportLocked() {
        markerTransport?.close()
        markerTransport = null
        commandTransport?.close()
        commandTransport = null
    }

    private fun markerFromEvent(event: JSONObject): JSONObject {
        val payload = JSONObject(event.toString())
        val eventType = event.optString("type", "")
        val blockIndex = event.optString("block_index", event.optString("block_id", ""))
        val trialUid = event.optString("trial_uid", "")
        val participantId = participantMetadata.optString("participant_id", "")
        val partSessionId = participantMetadata.optString("part_session_id", "")
        val partNumber = participantMetadata.optString("part_number", "")
        return JSONObject()
            .put("marker_version", "2.0")
            .put("event_id", event.optInt("event_id"))
            .put("event_type", eventType)
            .put("event_code", phoneEventCode(eventType))
            .put("trigger_key", phoneTriggerKey(eventType, blockIndex, trialUid))
            .put("marker_name", phoneMarkerName(participantId, eventType, blockIndex, trialUid, event))
            .put("session_id", participantMetadata.optString("session_id", ""))
            .put("participant_id", participantId)
            .put("session_group_id", participantMetadata.optString("session_group_id", ""))
            .put("part_session_id", partSessionId)
            .put("part_number", partNumber)
            .put("block_index", blockIndex)
            .put("trial_uid", trialUid)
            .put("timestamp_quality", "android_elapsed_realtime")
            .put("phone_unix_ms", event.optLong("phone_unix_ms"))
            .put("phone_elapsed_realtime_ms", event.optLong("phone_elapsed_realtime_ms"))
            .put("payload_json", payload.toString())
    }

    private fun summaryLocked(): JSONObject =
        JSONObject()
            .put("started_unix_ms", startedUnixMs)
            .put("completed_unix_ms", completedUnixMs)
            .put("total_event_count", events.size)
            .put("tap_count", tapCount)
            .put("valid_tap_count", validTapCount)
            .put("phone_playback_paused", playbackGate.isPaused())
            .put("phone_pause_count", phonePauseCount)
            .put("phone_resume_count", phoneResumeCount)
            .put("stop_after_block_requested", stopAfterBlockRequested)
            .put("phone_stop_after_block_request_count", phoneStopAfterBlockRequestCount)
            .put("stop_after_block_boundary_recorded", stopAfterBlockBoundaryRecorded)
            .put("phone_topup_skipped_by_stop_after_block", phoneTopupSkippedByStopAfterBlock)
            .put("completion_reason", completionReason)
            .put("block_paused_accumulated_ms", blockPausedAccumulatedMs + currentLivePauseDurationMs())
            .put("lsl_marker_mirror_count", lslMarkers.size)
            .put("native_lsl_transport_available", latestLslRuntimeStatus.optBoolean("native_transport_available", false))
            .put("native_lsl_marker_transport_enabled", latestLslRuntimeStatus.optBoolean("native_marker_transport_enabled", false))
            .put("native_lsl_command_receiver_available", latestLslRuntimeStatus.optBoolean("command_receiver_available", false))
            .put("native_lsl_timestamp_strategy", "android_elapsed_realtime_plus_open_lsl_clock_offset")
            .put("native_lsl_clock_offset_s", nativeLslClockOffsetS)
            .put("native_lsl_pushed_count", nativeLslPushedCount)
            .put("native_lsl_failed_count", nativeLslFailedCount)
            .put("native_lsl_command_received_count", nativeLslCommandReceivedCount)
            .put("native_lsl_command_ack_count", nativeLslCommandAckCount)
            .put("native_lsl_command_ack_failed_count", nativeLslCommandAckFailedCount)
            .put("native_lsl_command_rejected_count", nativeLslCommandRejectedCount)
            .put("command_diary_count", commandDiary.size)
}

private fun phoneRunPackageManifestText(runPackage: MobileRunPackage): String =
    runPackage.rawManifestJson.ifBlank {
        JSONObject()
            .put("schema", MOBILE_PACKAGE_SCHEMA)
            .put("package_id", runPackage.packageId)
            .put("participant_id", runPackage.participantId)
            .put("session_id", runPackage.sessionId)
            .put("session_group_id", runPackage.sessionGroupId)
            .put("part_session_id", runPackage.partSessionId)
            .put("part_number", runPackage.partNumber)
            .put("title", runPackage.title)
            .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
            .put("block_count", runPackage.blocks.size)
            .put("asset_count", runPackage.assets.size)
            .put("building_block_count", runPackage.buildingBlocks.size)
            .put("schedule_hash", runPackage.reconstruction.scheduleHash)
            .toString(2)
    }

private fun phoneRunReconstructionArtifact(runPackage: MobileRunPackage, manifestSha256: String): JSONObject =
    JSONObject()
        .put("schema", "pps-mobile-phone-run-reconstruction.v1")
        .put("package_id", runPackage.packageId)
        .put("participant_id", runPackage.participantId)
        .put("session_id", runPackage.sessionId)
        .put("session_group_id", runPackage.sessionGroupId)
        .put("part_session_id", runPackage.partSessionId)
        .put("part_number", runPackage.partNumber)
        .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
        .put("run_package_manifest_sha256", manifestSha256)
        .put(
            "reconstruction",
            JSONObject()
                .put("schema", runPackage.reconstruction.schema)
                .put("authority", runPackage.reconstruction.authority)
                .put("fallback_execution_strategy", runPackage.reconstruction.fallbackExecutionStrategy)
                .put("preferred_lightweight_strategy", runPackage.reconstruction.preferredLightweightStrategy)
                .put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)
                .put("source_run_setup_sha256", runPackage.reconstruction.sourceRunSetupSha256)
                .put("schedule_hash", runPackage.reconstruction.scheduleHash)
                .put("building_block_count", runPackage.reconstruction.buildingBlockCount)
                .put("block_count", runPackage.reconstruction.blockCount)
                .put("trial_count", runPackage.reconstruction.trialCount),
        )
        .put(
            "lsl",
            JSONObject()
                .put("schema", runPackage.lsl.schema)
                .put("runtime_authority", runPackage.lsl.runtimeAuthority)
                .put("rich_markers_name", runPackage.lsl.richMarkersName)
                .put("numeric_triggers_name", runPackage.lsl.numericTriggersName)
                .put("command_signals_name", runPackage.lsl.commandSignalsName)
                .put("command_acks_name", runPackage.lsl.commandAcksName)
                .put("native_android_lsl_required", runPackage.lsl.nativeAndroidLslRequired)
                .put("current_android_source_behavior", runPackage.lsl.currentAndroidSourceBehavior),
        )
        .put(
            "assets",
            JSONArray().also { array ->
                runPackage.assets.forEach { asset ->
                    array.put(
                        JSONObject()
                            .put("asset_id", asset.assetId)
                            .put("filename", asset.filename)
                            .put("role", asset.role)
                            .put("media_type", asset.mediaType)
                            .put("size_bytes", asset.sizeBytes)
                            .put("sha256", asset.sha256),
                    )
                }
            },
        )
        .put(
            "building_blocks",
            JSONArray().also { array ->
                runPackage.buildingBlocks.forEach { buildingBlock ->
                    array.put(
                        JSONObject()
                            .put("asset_id", buildingBlock.assetId)
                            .put("filename", buildingBlock.filename)
                            .put("role", buildingBlock.role)
                            .put("sha256", buildingBlock.sha256)
                            .put("trial_type", buildingBlock.trialType)
                            .put("family", buildingBlock.family)
                            .put("row_label", buildingBlock.rowLabel)
                            .put("soa_ms", buildingBlock.soaMs)
                            .put("noise_type", buildingBlock.noiseType)
                            .put("duration_s", buildingBlock.durationS)
                            .put("tactile_onset_s", buildingBlock.tactileOnsetS)
                            .put("response_window_onset_s", buildingBlock.responseWindowOnsetS),
                    )
                }
            },
        )
        .put(
            "blocks",
            JSONArray().also { array ->
                runPackage.blocks.forEach { block ->
                    array.put(
                        JSONObject()
                            .put("block_id", block.blockId)
                            .put("index", block.index)
                            .put("label", block.label)
                            .put("duration_s", block.durationS)
                            .put("trial_count", block.trialCount)
                            .put("audio_asset_id", block.audioAssetId)
                            .put(
                                "trial_building_block_asset_ids",
                                JSONArray().also { ids ->
                                    block.trials.forEach { trial -> ids.put(trial.buildingBlockAssetId) }
                                },
                            )
                            .put("tactile_cue_count", block.tactileCues.size),
                    )
                }
            },
        )

private fun phoneParticipantMetadata(
    runPackage: MobileRunPackage,
    age: String,
    handedness: String,
    gender: String,
    tactileThreshold: String,
    hapticCalibration: JSONObject? = null,
): JSONObject {
    val source = if (hapticCalibration != null) "android_haptic_calibration" else "manual_entry"
    val payload = JSONObject()
        .put("schema", "pps-android-phone-participant-metadata.v1")
        .put("participant_id", runPackage.participantId)
        .put("session_id", runPackage.sessionId)
        .put("session_group_id", runPackage.sessionGroupId)
        .put("part_session_id", runPackage.partSessionId)
        .put("part_number", runPackage.partNumber)
        .put("age_years", age)
        .put("handedness", handedness)
        .put("gender", gender)
        .put("tactile_threshold_percent", tactileThreshold)
        .put("tactile_threshold_source", source)
        .put("stream_privacy", "metadata_payload_only")
    if (hapticCalibration != null) {
        payload
            .put("tactile_threshold_calibration_schema", hapticCalibration.optString("schema", PHONE_HAPTIC_CALIBRATION_SCHEMA))
            .put("tactile_threshold_calibration_status", hapticCalibration.optString("status", ""))
    }
    return payload
}

private fun phoneHapticCapability(context: Context, hapticCalibration: JSONObject? = null): JSONObject {
    val vibrator = resolveVibrator(context)
    val hasVibrator = vibrator?.hasVibrator() == true
    val hasAmplitude = hasVibrator && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && vibrator?.hasAmplitudeControl() == true
    val payload = JSONObject()
        .put("schema", "pps-android-haptic-capability.v1")
        .put("has_vibrator", hasVibrator)
        .put("has_amplitude_control", hasAmplitude)
        .put("calibration_policy", if (hasAmplitude) "amplitude_percent_supported" else "binary_detection_only")
        .put("device_model", Build.MODEL ?: "")
        .put("android_sdk", Build.VERSION.SDK_INT)
    if (hapticCalibration != null) {
        payload
            .put("calibration_result", JSONObject(hapticCalibration.toString()))
            .put("calibration_status", hapticCalibration.optString("status", ""))
            .put("recommended_threshold_percent", hapticCalibration.opt("recommended_threshold_percent"))
            .put("recommended_amplitude", hapticCalibration.optInt("recommended_amplitude", PHONE_HAPTIC_DEFAULT_AMPLITUDE))
    }
    return payload
}

private fun resolveVibrator(context: Context): Vibrator? =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val manager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
        manager.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }

private fun vibratePhone(context: Context, amplitude: Int = VibrationEffect.DEFAULT_AMPLITUDE) {
    val vibrator = resolveVibrator(context) ?: return
    if (!vibrator.hasVibrator()) return
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        val resolvedAmplitude = if (amplitude in 1..255 || amplitude == VibrationEffect.DEFAULT_AMPLITUDE) {
            amplitude
        } else {
            VibrationEffect.DEFAULT_AMPLITUDE
        }
        vibrator.vibrate(VibrationEffect.createOneShot(60L, resolvedAmplitude))
    } else {
        @Suppress("DEPRECATION")
        vibrator.vibrate(60L)
    }
}

private fun phoneEventCode(eventType: String): Int =
    when (eventType) {
        "session_metadata" -> 8
        "run_start" -> 1
        "run_complete" -> 2
        "block_start" -> 10
        "block_complete" -> 11
        "vibration_cue" -> 21
        "tap" -> 30
        "phone_scheduled_block_materialization" -> 34
        "phone_topup_materialization" -> 35
        "operator_command" -> 41
        "phone_playback_pause" -> 42
        "phone_playback_resume" -> 43
        "phone_stop_after_block_request" -> 44
        "phone_stop_after_block_boundary" -> 45
        else -> 500
    }

private fun phoneTriggerKey(eventType: String, blockIndex: String, trialUid: String): String =
    if (trialUid.isNotBlank()) {
        "trial:$trialUid:$eventType"
    } else if (blockIndex.isNotBlank()) {
        "block:$blockIndex:$eventType"
    } else {
        "control:$eventType"
    }

private fun phoneMarkerName(
    participantId: String,
    eventType: String,
    blockIndex: String,
    trialUid: String,
    event: JSONObject,
): String {
    val participant = participantId.ifBlank { "PXX" }.markerToken()
    val block = blockIndex.ifBlank { "blockXX" }.markerToken()
    val row = event.optString("row_label", "").markerToken()
    val noise = event.optString("noise_type", "").markerToken()
    val soa = event.optString("soa_ms", "").markerToken()
    return listOf(participant, block, row, noise, if (soa.isNotBlank()) "SOA$soa" else "", trialUid.markerToken(), eventType.markerToken())
        .filter { it.isNotBlank() }
        .joinToString("_")
}

private suspend fun RunnerClient.awaitMobilePackage(packageId: String): MobileRunPackage =
    suspendCancellableCoroutine { continuation ->
        fetchMobilePackage(
            packageId,
            onPackage = { if (continuation.isActive) continuation.resume(it) },
            onError = { if (continuation.isActive) continuation.resumeWithException(RuntimeException(it)) },
        )
    }

private suspend fun RunnerClient.awaitDownloadMobileAsset(packageId: String, assetId: String, targetFile: File): File =
    suspendCancellableCoroutine { continuation ->
        downloadMobileAsset(
            packageId,
            assetId,
            targetFile,
            onDownloaded = { if (continuation.isActive) continuation.resume(it) },
            onError = { if (continuation.isActive) continuation.resumeWithException(RuntimeException(it)) },
        )
    }

private suspend fun RunnerClient.awaitPostMobileEvents(runId: String, payload: JSONObject): JSONObject =
    suspendCancellableCoroutine { continuation ->
        postMobileEvents(
            runId,
            payload,
            onAccepted = { if (continuation.isActive) continuation.resume(it) },
            onError = { if (continuation.isActive) continuation.resumeWithException(RuntimeException(it)) },
        )
    }

private suspend fun RunnerClient.awaitPostMobileComplete(runId: String, payload: JSONObject): JSONObject =
    suspendCancellableCoroutine { continuation ->
        postMobileComplete(
            runId,
            payload,
            onAccepted = { if (continuation.isActive) continuation.resume(it) },
            onError = { if (continuation.isActive) continuation.resumeWithException(RuntimeException(it)) },
        )
    }

private fun mobilePackageDir(context: Context, packageId: String): File =
    File(context.filesDir, "mobile_packages/${safeFileName(packageId)}")

private fun mobileAssetFile(context: Context, packageId: String, asset: MobileAsset): File =
    File(mobilePackageDir(context, packageId), "${safeFileName(asset.assetId)}__${safeFileName(asset.filename)}")

private fun phoneRunDir(context: Context, runId: String): File =
    File(context.filesDir, "phone_runs/${safeFileName(runId)}")

private fun writePhoneEventsCsv(path: File, events: List<JSONObject>) {
    val keys = linkedSetOf<String>()
    events.forEach { event ->
        event.keys().forEach { key ->
            val value = event.opt(key)
            if (value == null || value is String || value is Number || value is Boolean) {
                keys.add(key)
            }
        }
    }
    if (keys.isEmpty()) return
    path.parentFile?.mkdirs()
    path.writeText(
        buildString {
            append(keys.joinToString(",") { csvCell(it) })
            append("\n")
            events.forEach { event ->
                append(keys.joinToString(",") { key -> csvCell(event.opt(key)?.toString().orEmpty()) })
                append("\n")
            }
        },
        Charsets.UTF_8,
    )
}

private fun writePhoneTriggerCodesCsv(path: File, markers: List<JSONObject>) {
    if (markers.isEmpty()) return
    path.parentFile?.mkdirs()
    path.writeText(
        buildString {
            append("event_id,event_code,event_type,trigger_key,phone_elapsed_realtime_ms\n")
            markers.forEach { marker ->
                append(
                    listOf(
                        marker.optString("event_id", ""),
                        marker.optString("event_code", ""),
                        marker.optString("event_type", ""),
                        marker.optString("trigger_key", ""),
                        marker.optString("phone_elapsed_realtime_ms", ""),
                    ).joinToString(",") { csvCell(it) },
                )
                append("\n")
            }
        },
        Charsets.UTF_8,
    )
}

private fun writeCommandDiaryJsonl(path: File, rows: List<JSONObject>) {
    if (rows.isEmpty()) return
    path.parentFile?.mkdirs()
    path.writeText(
        buildString {
            rows.forEach { row ->
                append(row.toString())
                append("\n")
            }
        },
        Charsets.UTF_8,
    )
}

private fun exportPhoneRunZip(context: Context, runDir: File): File {
    require(runDir.isDirectory) { "No completed phone session is available to export." }
    val exportDir = File(context.cacheDir, "exports")
    exportDir.mkdirs()
    val zip = File(exportDir, "${safeFileName(runDir.name)}.zip")
    ZipOutputStream(FileOutputStream(zip)).use { output ->
        addZipEntries(output, runDir, "")
        addPhoneRunCatalogSnapshot(output, context.filesDir)
        addPhoneOwnedExportsSnapshot(output, context.filesDir)
    }
    return zip
}

private fun addPhoneRunCatalogSnapshot(output: ZipOutputStream, filesDir: File) {
    val catalogRoot = File(filesDir, "phone_run_catalog")
    if (catalogRoot.isDirectory) {
        addZipEntries(output, catalogRoot, "phone_run_catalog")
    }
}

private fun addPhoneOwnedExportsSnapshot(output: ZipOutputStream, filesDir: File) {
    val exportRoot = File(filesDir, "phone_owned_exports")
    if (exportRoot.isDirectory) {
        addZipEntries(output, exportRoot, "phone_owned_exports")
    }
}

private fun addZipEntries(output: ZipOutputStream, root: File, prefix: String) {
    root.listFiles()?.sortedBy { it.name }?.forEach { file ->
        val entryName = if (prefix.isBlank()) file.name else "$prefix/${file.name}"
        if (file.isDirectory) {
            addZipEntries(output, file, entryName)
        } else if (file.isFile) {
            output.putNextEntry(ZipEntry(entryName))
            file.inputStream().use { input -> input.copyTo(output) }
            output.closeEntry()
        }
    }
}

private fun createPhoneRunBundle(context: Context, artifactDirs: List<String>): File {
    val bundle = File(context.filesDir, "phone_run_bundles/full-${System.currentTimeMillis()}")
    bundle.mkdirs()
    val manifest = JSONArray()
    artifactDirs.forEachIndexed { index, rawDir ->
        val source = File(rawDir)
        if (!source.isDirectory) return@forEachIndexed
        val target = File(bundle, "part-${index + 1}-${safeFileName(source.name)}")
        copyDirectory(source, target)
        manifest.put(JSONObject().put("part_index", index + 1).put("source_dir", source.absolutePath).put("bundle_dir", target.name))
    }
    File(bundle, "bundle_manifest.json").writeText(
        JSONObject()
            .put("schema", "pps-mobile-phone-run-bundle.v1")
            .put("created_unix_ms", System.currentTimeMillis())
            .put("parts", manifest)
            .toString(2),
        Charsets.UTF_8,
    )
    return bundle
}

private fun copyDirectory(source: File, target: File) {
    target.mkdirs()
    source.listFiles()?.forEach { file ->
        val destination = File(target, file.name)
        if (file.isDirectory) {
            copyDirectory(file, destination)
        } else if (file.isFile) {
            file.copyTo(destination, overwrite = true)
        }
    }
}

private fun sharePhoneRunZip(context: Context, zip: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", zip)
    val intent = Intent(Intent.ACTION_SEND)
        .setType("application/zip")
        .putExtra(Intent.EXTRA_STREAM, uri)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    context.startActivity(Intent.createChooser(intent, "Export PPS phone session"))
}

private fun csvCell(value: String): String = "\"${value.replace("\"", "\"\"")}\""

private fun jsonStringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }

private fun String.markerToken(): String =
    trim()
        .replace("+", "plus")
        .map { char -> if (char.isLetterOrDigit()) char else '_' }
        .joinToString("")
        .trim('_')

private fun safeFileName(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "asset" }

internal fun sha256File(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buffer = ByteArray(1024 * 1024)
        while (true) {
            val read = input.read(buffer)
            if (read <= 0) break
            digest.update(buffer, 0, read)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

private fun sha256Text(value: String): String {
    val digest = MessageDigest.getInstance("SHA-256")
    digest.update(value.toByteArray(Charsets.UTF_8))
    return digest.digest().joinToString("") { "%02x".format(it) }
}

private fun formatBytes(value: Long): String =
    when {
        value >= 1024L * 1024L * 1024L -> String.format("%.1f GB", value / (1024.0 * 1024.0 * 1024.0))
        value >= 1024L * 1024L -> String.format("%.1f MB", value / (1024.0 * 1024.0))
        value >= 1024L -> String.format("%.1f KB", value / 1024.0)
        else -> "$value B"
    }

private fun formatMillisecondsShort(value: Long): String = formatSeconds(value / 1000.0)

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
