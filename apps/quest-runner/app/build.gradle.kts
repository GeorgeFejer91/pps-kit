import org.gradle.api.GradleException
import org.gradle.api.tasks.Exec
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.jetbrains.kotlin.android)
  alias(libs.plugins.jetbrains.kotlin.compose)
  alias(libs.plugins.meta.spatial)
}

val pinnedNdkVersion = "27.0.12077973"
val rustTarget = "aarch64-linux-android"
val rustLibraryFileName = "libpps_quest_core.so"
val rustCrateDir =
    rootProject.file(
        providers.gradleProperty("ppsRustCoreDir").orElse("native/pps-quest-core").get(),
    )
val repositoryRoot = rootProject.projectDir.resolve("../..").canonicalFile
val rustTargetDir = layout.buildDirectory.dir("rust-target")
val generatedRustJniDir = layout.buildDirectory.dir("generated/rustJniLibs")
val generatedRustLibrary = generatedRustJniDir.map { it.file("arm64-v8a/$rustLibraryFileName") }

android {
  namespace = "io.ppskit.questrunner"
  compileSdk = 34
  ndkVersion = pinnedNdkVersion

  defaultConfig {
    applicationId = "io.ppskit.questrunner"
    minSdk = 34
    targetSdk = 34
    versionCode = 1
    versionName = "0.1.0-preview"
    buildConfigField("boolean", "BRSP_REMOTE_ENABLED", "true")

    ndk { abiFilters += "arm64-v8a" }
  }

  buildTypes {
    debug {
      isJniDebuggable = true
    }
    release {
      isMinifyEnabled = true
      proguardFiles(
          getDefaultProguardFile("proguard-android-optimize.txt"),
          "proguard-rules.pro",
      )
    }
  }

  buildFeatures {
    buildConfig = true
    compose = true
  }

  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
  }

  packaging {
    jniLibs.useLegacyPackaging = false
    resources.excludes += "META-INF/LICENSE"
  }

  // Kotlin-only preview builds must never package a stale native library left
  // by an earlier full build. When Rust is explicitly skipped, omit the
  // generated JNI source directory altogether.
  if (!providers.gradleProperty("skipRustBuild").isPresent) {
    sourceSets["main"].jniLibs.srcDir(generatedRustJniDir)
  }

  testOptions { unitTests.isReturnDefaultValues = true }
}

spatial { allowUsageDataCollection.set(false) }

dependencies {
  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.activity.compose)
  implementation(platform(libs.androidx.compose.bom))
  implementation(libs.androidx.compose.foundation)
  implementation(libs.androidx.compose.material3)
  implementation(libs.androidx.compose.ui)
  implementation(libs.androidx.compose.ui.tooling.preview)
  implementation(libs.kotlinx.coroutines.android)
  implementation(libs.okhttp)

  implementation(libs.meta.spatial.sdk.base)
  implementation(libs.meta.spatial.sdk.compose)
  implementation(libs.meta.spatial.sdk.isdk)
  implementation(libs.meta.spatial.sdk.toolkit)
  implementation(libs.meta.spatial.sdk.vr)

  testImplementation(libs.junit)
  testImplementation(libs.json)
  testImplementation(libs.okhttp.mockwebserver)
}

fun resolveNdkHome(): File {
  val explicitNdk =
      providers.gradleProperty("ppsNdkDir").orNull
          ?: System.getenv("ANDROID_NDK_HOME")
          ?: System.getenv("ANDROID_NDK_ROOT")
  if (!explicitNdk.isNullOrBlank()) {
    return file(explicitNdk)
  }

  val sdkRoot = System.getenv("ANDROID_SDK_ROOT") ?: System.getenv("ANDROID_HOME")
  if (!sdkRoot.isNullOrBlank()) {
    return file("$sdkRoot/ndk/$pinnedNdkVersion")
  }

  throw GradleException(
      "Rust/Android build requires ANDROID_NDK_HOME, ANDROID_NDK_ROOT, " +
          "ANDROID_SDK_ROOT, ANDROID_HOME, or -PppsNdkDir.",
  )
}

fun resolveNdkLinker(ndkHome: File): File {
  val osName = System.getProperty("os.name").lowercase()
  val hostCandidates =
      when {
        osName.contains("win") -> listOf("windows-x86_64")
        osName.contains("mac") -> listOf("darwin-x86_64", "darwin-aarch64")
        else -> listOf("linux-x86_64")
      }
  val executableCandidates =
      if (osName.contains("win")) {
        listOf("aarch64-linux-android34-clang.cmd", "aarch64-linux-android34-clang")
      } else {
        listOf("aarch64-linux-android34-clang")
      }

  for (host in hostCandidates) {
    for (executable in executableCandidates) {
      val candidate = ndkHome.resolve("toolchains/llvm/prebuilt/$host/bin/$executable")
      if (candidate.isFile) return candidate
    }
  }

  throw GradleException(
      "Could not find the API 34 AArch64 clang linker under ${ndkHome.absolutePath}.",
  )
}

fun resolveCargo(): String {
  val explicitCargo = System.getenv("CARGO")
  if (!explicitCargo.isNullOrBlank()) return explicitCargo

  val cargoFileName = if (System.getProperty("os.name").lowercase().contains("win")) "cargo.exe" else "cargo"
  val userCargo = file("${System.getProperty("user.home")}/.cargo/bin/$cargoFileName")
  return if (userCargo.isFile) userCargo.absolutePath else "cargo"
}

val buildRustArm64 by tasks.registering(Exec::class) {
  group = "build"
  description = "Builds the local/shared pps_quest_core Rust cdylib for Quest arm64."
  notCompatibleWithConfigurationCache("Resolves the host-specific Cargo and Android NDK toolchain at execution time.")

  inputs.dir(rustCrateDir)
  inputs.file(repositoryRoot.resolve("Cargo.toml"))
  inputs.file(repositoryRoot.resolve("Cargo.lock"))
  inputs.dir(repositoryRoot.resolve("packages/pps-brsp"))
  inputs.dir(repositoryRoot.resolve("packages/pps-contracts"))
  inputs.dir(repositoryRoot.resolve("packages/pps-runner-core"))
  outputs.file(generatedRustLibrary)
  onlyIf { !providers.gradleProperty("skipRustBuild").isPresent }

  doFirst {
    val manifest = rustCrateDir.resolve("Cargo.toml")
    if (!manifest.isFile) {
      throw GradleException(
          "Expected a pps_quest_core Cargo manifest at ${manifest.absolutePath}. " +
              "Set -PppsRustCoreDir=<path> to use the shared implementation.",
      )
    }

    val linker = resolveNdkLinker(resolveNdkHome())
    environment("CARGO_TARGET_DIR", rustTargetDir.get().asFile.absolutePath)
    environment("CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER", linker.absolutePath)
    commandLine(
        resolveCargo(),
        "build",
        "--manifest-path",
        manifest.absolutePath,
        "--target",
        rustTarget,
        "--release",
        "--locked",
    )
  }

  doLast {
    val builtLibrary =
        rustTargetDir.get().asFile.resolve("$rustTarget/release/$rustLibraryFileName")
    if (!builtLibrary.isFile) {
      throw GradleException("Cargo completed without producing ${builtLibrary.absolutePath}.")
    }
    copy {
      from(builtLibrary)
      into(generatedRustJniDir.get().dir("arm64-v8a"))
    }
  }
}

tasks.configureEach {
  if (
      name == "mergeDebugJniLibFolders" ||
          name == "mergeReleaseJniLibFolders" ||
          name == "mergeDebugNativeLibs" ||
          name == "mergeReleaseNativeLibs"
  ) {
    dependsOn(buildRustArm64)
  }
}
