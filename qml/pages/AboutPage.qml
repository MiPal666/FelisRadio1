import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: page
    property string buildVersion
    readonly property real cutoutDepth: Screen.hasCutouts ? Math.max(0, Screen.topCutout.y + Screen.topCutout.height) : 0
    allowedOrientations: Orientation.Portrait
    SilicaFlickable {
        anchors.fill: parent
        anchors.topMargin: page.cutoutDepth
        contentHeight: content.height + Theme.paddingLarge
        Column {
            id: content
            width: parent.width
            spacing: Theme.paddingMedium
            PageHeader { title: qsTr("About") }
            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Theme.itemSizeHuge * 1.4
                height: width
                source: "../images/felisradio1.png"
                sourceSize.width: Math.ceil(width)
                sourceSize.height: Math.ceil(height)
            }
            SectionHeader { text: "Felis Radio 1" }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("Version %1").arg(page.buildVersion)
                font.pixelSize: Theme.fontSizeSmall
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("An unofficial Radio 1 player for Sailfish OS, with local playback, Chromecast output and live track information.")
                textFormat: Text.PlainText; wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("Created by Michal Kasík (MiPal), with assistance from Klára (AI).")
                wrapMode: Text.Wrap; font.pixelSize: Theme.fontSizeSmall
            }
            Button { anchors.horizontalCenter: parent.horizontalCenter; text: qsTr("Source code on GitHub"); onClicked: Qt.openUrlExternally("https://github.com/MiPal666/FelisRadio1") }
            SectionHeader { text: qsTr("About Radio 1") }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("Radio 1 is a Czech radio station with alternative music programming, spanning guitar music, electronic music and many other genres. It also features specialist shows and cultural coverage.")
                textFormat: Text.PlainText; wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
            }
            Button { anchors.horizontalCenter: parent.horizontalCenter; text: "www.radio1.cz"; onClicked: Qt.openUrlExternally("https://www.radio1.cz/") }
            SectionHeader { text: qsTr("License") }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("This application is free software under the GNU General Public License, version 3 or any later version (GPL-3.0-or-later). It comes without warranty. Third-party components retain their own licenses.")
                textFormat: Text.PlainText; wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
            }
            Button { anchors.horizontalCenter: parent.horizontalCenter; text: qsTr("GNU GPL v3"); onClicked: Qt.openUrlExternally("https://www.gnu.org/licenses/gpl-3.0.html") }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2 * x
                text: qsTr("Radio 1's name, logo and broadcast belong to their respective rights holders. This application is not an official Radio 1 product.")
                textFormat: Text.PlainText; wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeExtraSmall; color: Theme.secondaryColor
            }
        }
        VerticalScrollDecorator { }
    }
}
