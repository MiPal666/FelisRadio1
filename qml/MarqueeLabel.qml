import QtQuick 2.6
import Sailfish.Silica 1.0

Item {
    id: root
    property string text: ""
    property bool active: true
    property real fontSize: Theme.fontSizeLarge
    readonly property real overflow: Math.max(0, caption.implicitWidth - width)
    height: caption.height
    clip: true
    function reset() {
        travel.stop()
        caption.x = overflow > 0 ? 0 : Math.max(0, (width - caption.implicitWidth) / 2)
        if (active && overflow > 1) travel.start()
    }
    onTextChanged: reset()
    onWidthChanged: reset()
    onOverflowChanged: reset()
    onActiveChanged: reset()
    Component.onCompleted: reset()
    Label {
        id: caption
        text: root.text
        textFormat: Text.PlainText
        font.pixelSize: root.fontSize
        color: Theme.highlightColor
        onImplicitWidthChanged: root.reset()
    }
    SequentialAnimation {
        id: travel
        loops: Animation.Infinite
        PauseAnimation { duration: 1400 }
        NumberAnimation {
            target: caption; property: "x"; from: 0; to: -root.overflow
            duration: Math.max(1500, root.overflow / 35 * 1000)
            easing.type: Easing.Linear
        }
        PauseAnimation { duration: 1400 }
        NumberAnimation {
            target: caption; property: "x"; from: -root.overflow; to: 0
            duration: Math.max(1500, root.overflow / 35 * 1000)
            easing.type: Easing.Linear
        }
    }
}
