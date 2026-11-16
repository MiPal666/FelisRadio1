import QtQuick 2.6
import Sailfish.Silica 1.0

CoverBackground {
    id: cover
    property var backend
    Item {
        anchors.fill: parent
        anchors.margins: Theme.paddingMedium
        anchors.bottomMargin: Math.max(Theme.itemSizeSmall,
            cover.coverActionArea ? cover.coverActionArea.height : 0) + Theme.paddingMedium
        Image {
            id: logo
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width * 0.8,
                Math.max(0, parent.height - caption.height - Theme.paddingMedium))
            height: width
            source: "../images/felisradio1.png"
            sourceSize.width: Math.ceil(width)
            sourceSize.height: Math.ceil(width)
            fillMode: Image.PreserveAspectFit
        }
        Label {
            id: caption
            anchors.bottom: parent.bottom
            width: parent.width
            text: backend.title
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            font.pixelSize: Theme.fontSizeSmall
        }
    }
    CoverActionList {
        enabled: backend.ready
        CoverAction {
            iconSource: backend.wanted || backend.playing || backend.switching
                ? "image://theme/icon-cover-cancel" : "image://theme/icon-cover-play"
            onTriggered: backend.toggle()
        }
    }
}
