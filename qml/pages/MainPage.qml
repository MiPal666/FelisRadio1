import QtQuick 2.6
import Sailfish.Silica 1.0
import ".."

Page {
    id: page
    property var backend
    allowedOrientations: Orientation.Portrait
    readonly property real cutoutDepth: Screen.hasCutouts ? Math.max(0, Screen.topCutout.y + Screen.topCutout.height) : 0
    SilicaFlickable {
        id: playerFlick
        anchors.fill: parent
        anchors.topMargin: page.cutoutDepth
        anchors.bottomMargin: footer.height + Theme.paddingSmall
        clip: true
        contentHeight: content.height + Theme.paddingLarge
        PullDownMenu {
            MenuItem { text: qsTr("About"); onClicked: pageStack.push(Qt.resolvedUrl("AboutPage.qml"), {buildVersion: backend.diagnosticBuild}) }
            MenuItem { text: qsTr("Refresh devices"); enabled: backend.ready; onClicked: backend.scan() }
        }
        Column {
            id: content
            width: parent.width
            // Equal spacing between groups; related controls stay together.
            spacing: Theme.paddingLarge * 1.5
            PageHeader { title: "Felis Radio 1" }
            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width * 0.72, playerFlick.height * 0.36)
                height: width
                source: "../images/felisradio1.png"
                sourceSize.width: Math.ceil(width)
                sourceSize.height: Math.ceil(height)
                fillMode: Image.PreserveAspectFit
            }
            MarqueeLabel {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                text: backend.title
                active: page.status === PageStatus.Active && Qt.application.state === Qt.ApplicationActive
                fontSize: Theme.fontSizeLarge
            }
            Column {
                width: parent.width
                spacing: Theme.paddingMedium
                Label {
                    x: Theme.horizontalPageMargin
                    width: parent.width - 2 * x
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    text: backend.stateText
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.secondaryColor
                }
                Button {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: backend.wanted || backend.playing || backend.switching ? qsTr("Stop") : qsTr("Play")
                    enabled: backend.ready
                    onClicked: backend.toggle()
                }
                BusyIndicator {
                    anchors.horizontalCenter: parent.horizontalCenter
                    running: backend.buffering || backend.switching
                    visible: running
                    size: BusyIndicatorSize.Medium
                    height: visible ? implicitHeight : 0
                }
            }
            Column {
                width: parent.width
                spacing: 0
                Slider {
                    width: parent.width
                    label: qsTr("Volume · ") + backend.outputName
                    minimumValue: 0
                    maximumValue: 1
                    stepSize: 0.01
                    value: backend.volume
                    valueText: Math.round(value * 100) + " %"
                    enabled: backend.ready && !backend.switching && !backend.disconnected
                    onSliderValueChanged: if (down) backend.setVolume(sliderValue)
                }
                TextSwitch {
                    width: parent.width
                    text: qsTr("Mute")
                    automaticCheck: false
                    checked: backend.muted
                    enabled: backend.ready && !backend.switching && !backend.disconnected
                    onClicked: backend.setMuted(!backend.muted)
                }
            }
            InlineChoice {
                id: outputChoice
                width: parent.width
                label: qsTr("Audio output")
                selectedKey: backend.deviceId
                enabled: backend.ready && !backend.switching
                options: {
                    var rows = [{key: "local", title: qsTr("This phone")}]
                    var found = false
                    for (var i = 0; i < backend.devices.length; i++) {
                        var device = backend.devices[i]
                        rows.push({key: device.id, title: device.name})
                        if (device.id === backend.deviceId) found = true
                    }
                    if (backend.castSelected && !backend.disconnected && !found) rows.push({key: backend.deviceId, title: backend.outputName})
                    return rows
                }
                // Discovery is opt-in, rather than starting network scanning at launch.
                onOpening: {
                    backend.traceCast("output_menu.opening", null)
                    backend.scan()
                }
                onChosen: backend.selectOutput(key)
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: backend.scanning || backend.discoveryFailed
                text: backend.scanning ? qsTr("Searching for Cast devices…") : qsTr("Cannot find Cast devices. Try refreshing the list.")
                font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.Wrap
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                text: backend.errorMessage
                textFormat: Text.PlainText
                visible: text.length > 0
                color: Theme.highlightColor
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
            }
        }
        VerticalScrollDecorator { }
    }
    Item {
        id: footer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Theme.itemSizeSmall
        Label {
            anchors.left: parent.left
            anchors.leftMargin: Theme.horizontalPageMargin
            anchors.verticalCenter: parent.verticalCenter
            text: "www.radio1.cz"
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.highlightColor
            MouseArea { anchors.fill: parent; anchors.margins: -Theme.paddingSmall; onClicked: Qt.openUrlExternally("https://www.radio1.cz/") }
        }
        Label {
            anchors.right: parent.right
            anchors.rightMargin: Theme.horizontalPageMargin
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Build %1").arg(page.backend.diagnosticBuild)
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
        }
    }
}
