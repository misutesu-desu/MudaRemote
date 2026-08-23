import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val generatedPythonDir = layout.buildDirectory.dir("generated/mudaremote-python")
val generatedAndroidAssetsDir = layout.buildDirectory.dir("generated/android-assets")

// Stable release signing. The keystore lives outside git (android/keystore.properties,
// gitignored) locally, and is materialized from GitHub secrets in CI. When absent,
// builds fall back to the debug key so contributor environments still compile.
val keystoreProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}
val hasReleaseSigning = keystoreProperties.isNotEmpty()
val preparePythonRuntime by tasks.registering(Sync::class) {
    from(projectDir.parentFile.parentFile) {
        include("mudae_bot.py", "mudae_core/**/*.py")
    }
    from("src/main/python") { include("**/*.py") }
    into(generatedPythonDir)
}
val generateAndroidSchema by tasks.registering(Exec::class) {
    commandLine(
        "python",
        projectDir.parentFile.parentFile.resolve("android/generate_schema.py").absolutePath,
        projectDir.parentFile.parentFile.absolutePath,
        generatedAndroidAssetsDir.get().asFile.absolutePath,
    )
}

android {
    namespace = "com.mudaremote.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.mudaremote.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 12
        versionName = "1.2.4"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("mudaremote") {
                storeFile = rootProject.file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    buildTypes {
        create("mobile") {
            initWith(getByName("debug"))
            if (hasReleaseSigning) signingConfig = signingConfigs.getByName("mudaremote") else signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("debug")
        }
        create("ux") {
            initWith(getByName("mobile"))
            if (hasReleaseSigning) signingConfig = signingConfigs.getByName("mudaremote") else signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("mobile", "debug")
        }
        release {
            isMinifyEnabled = false
            if (hasReleaseSigning) signingConfig = signingConfigs.getByName("mudaremote")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    sourceSets.getByName("main") {
        assets.srcDir(generatedAndroidAssetsDir)
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            install("discord.py-self==2.0.1")
            install("requests>=2.31,<3")
        }
    }
    // Package the proven desktop engine directly. Android-only glue lives in
    // src/main/python, while this directory supplies mudae_bot.py and mudae_core.
    sourceSets {
        getByName("main") {
            setSrcDirs(listOf(generatedPythonDir.get().asFile))
        }
    }
}

tasks.matching { it.name.endsWith("PythonSources") }.configureEach {
    dependsOn(preparePythonRuntime)
}
tasks.matching { it.name.endsWith("Assets") }.configureEach {
    dependsOn(generateAndroidSchema)
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-ktx:1.10.0")
}
