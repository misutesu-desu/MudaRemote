plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val generatedPythonDir = layout.buildDirectory.dir("generated/mudaremote-python")
val generatedAndroidAssetsDir = layout.buildDirectory.dir("generated/android-assets")
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
        versionCode = 6
        versionName = "1.1.4"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        create("mobile") {
            initWith(getByName("debug"))
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("debug")
        }
        create("ux") {
            initWith(getByName("mobile"))
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("mobile", "debug")
        }
        release {
            isMinifyEnabled = false
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
