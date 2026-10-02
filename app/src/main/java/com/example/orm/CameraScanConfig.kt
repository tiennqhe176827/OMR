package com.example.orm

import android.util.Size
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy

/** A full 4:3 sensor stream retains enough pixels to read an A4 sheet directly. */
object CameraScanConfig {
    const val A4_ASPECT = 210f / 297f
    const val PREVIEW_ASPECT = 3f / 4f
    const val GUIDE_FILL = .96f

    fun analysis(): ImageAnalysis = ImageAnalysis.Builder()
        .setResolutionSelector(ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
            .setResolutionStrategy(ResolutionStrategy(Size(2560, 1920),
                ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
            .build())
        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
        .build()
}
