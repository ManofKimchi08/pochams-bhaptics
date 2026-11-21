import sys

from PySide6.QtWidgets import QApplication, QTabWidget

from ui import (
    QSignalBridge,
    FloatingOverlaySettingsDialog,
    FloatingVestOverlay,
    MiniVestPreviewWidget,
    SlantedHpBarWidget,
    CompactHudWindow,
    VisionDebugWidget,
    VideoWidget,
    EmbeddedHapticDetailView,
    BattleAnalyticsDialog,
    MainWindow,
)

__all__ = [
    "QTabWidget",
    "QSignalBridge",
    "FloatingOverlaySettingsDialog",
    "FloatingVestOverlay",
    "MiniVestPreviewWidget",
    "SlantedHpBarWidget",
    "CompactHudWindow",
    "VisionDebugWidget",
    "VideoWidget",
    "EmbeddedHapticDetailView",
    "BattleAnalyticsDialog",
    "MainWindow",
    "main",
]


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
