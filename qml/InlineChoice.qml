import QtQuick 2.6
import Sailfish.Silica 1.0

Item {
    id: choice
    property bool showButton: true
    property string label
    property string selectedKey
    property var options: []
    signal chosen(string key)
    signal opening()
    function close() { menu.close() }
    function open() { choice.opening(); menu.open(choice) }
    implicitHeight: button.height + (menu.parent === choice ? menu.height : 0)
    height: visible ? implicitHeight : 0
    // Discovery updates must not close the menu or recreate existing rows.
    function syncOptions() {
        if (!choices) return
        for (var i = 0; i < options.length; ++i) {
            var row = { optionKey: String(options[i].key), title: String(options[i].title),
                        available: options[i].enabled !== false }
            var existing = i
            while (existing < choices.count && choices.get(existing).optionKey !== row.optionKey) ++existing
            if (existing === choices.count) choices.insert(i, row)
            else {
                if (existing !== i) choices.move(existing, i, 1)
                choices.set(i, row)
            }
        }
        if (choices.count > options.length) choices.remove(options.length, choices.count - options.length)
    }
    onOptionsChanged: syncOptions()
    Component.onCompleted: syncOptions()
    ListModel { id: choices }
    Item {
        id: button
        width: parent.width
        height: choice.showButton ? valueButton.height : 0
        ValueButton {
            id: valueButton
            width: parent.width
            visible: choice.showButton
            label: choice.label
            value: {
                var selected = choice.options.filter(function(option) { return option.key === choice.selectedKey })
                return (selected.length ? selected[0].title : "") + " ▾"
            }
            onClicked: {
                if (menu.active) choice.close()
                else choice.open()
            }
        }
    }
    ContextMenu {
        id: menu
        Repeater {
            model: choices
            MenuItem {
                text: model.title
                enabled: model.available
                onClicked: choice.chosen(model.optionKey)
            }
        }
    }
}
