package io.ppskit.questrunner

import androidx.compose.ui.platform.ComposeView
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.createPanelEntity
import com.meta.spatial.vr.VRFeature
import io.ppskit.questrunner.core.RunnerCommandDispatcher
import io.ppskit.questrunner.core.RunnerCoreFactory

/** Sole owner of the immersive Activity, Spatial SDK scene, and panel lifecycle. */
class QuestRunnerActivity : AppSystemActivity() {
  private val panelController by lazy {
    RunnerPanelController(
        RunnerCommandDispatcher(
            RunnerCoreFactory.create(allowKotlinPreviewFallback = BuildConfig.DEBUG),
        ),
    )
  }
  private val relayController by lazy {
    RelayTargetController(
        enabled = BuildConfig.BRSP_REMOTE_ENABLED,
        allowCleartext = BuildConfig.DEBUG,
        onSnapshotChanged = panelController::refresh,
    )
  }

  override fun registerFeatures(): List<SpatialFeature> =
      listOf(
          VRFeature(this),
          ComposeFeature(),
      )

  override fun onSceneReady() {
    super.onSceneReady()
    scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)

    // Programmatic placement keeps this preview independent of Spatial Editor assets.
    Entity.createPanelEntity(
        R.id.runner_panel,
        Transform(Pose(Vector3(0f, 1.3f, 2f))),
    )
  }

  override fun registerPanels(): List<PanelRegistration> =
      listOf(
          ComposeViewPanelRegistration(
              R.id.runner_panel,
              composeViewCreator = { _, context ->
                ComposeView(context).apply {
                  setContent {
                    RunnerControlPanel(
                        panelController,
                        relayController,
                        BuildConfig.DEBUG,
                        relayController.available,
                    )
                  }
                }
              },
              settingsCreator = {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.8f, height = 1.5f),
                    style =
                        PanelStyleOptions(
                            themeResourceId = R.style.PanelAppThemeTransparent,
                        ),
                    display = DpPerMeterDisplayOptions(),
                )
              },
          ),
      )

  override fun onDestroy() {
    relayController.shutdown()
    super.onDestroy()
  }

  override fun onPause() {
    relayController.onHostPaused()
    super.onPause()
  }
}
