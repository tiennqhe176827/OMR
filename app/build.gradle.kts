plugins {
    id("com.chaquo.python")
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.orm"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.example.orm"
        minSdk = 31
        targetSdk = 37
        versionCode = 17
        versionName = "1.17"
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a", "x86_64") }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
    }
}

chaquopy {
    defaultConfig {
        version = "3.10"
        val localPython = rootProject.file(".tools/python310/tools/python.exe")
        if (localPython.exists()) buildPython(localPython.absolutePath)
        pip {
            install("numpy==1.26.2")
            install("opencv-python-headless==4.5.1.48")
        }
    }
}

dependencies {
    val cameraVersion = "1.4.2"
    implementation("androidx.camera:camera-camera2:$cameraVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraVersion")
    implementation("androidx.camera:camera-view:$cameraVersion")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
