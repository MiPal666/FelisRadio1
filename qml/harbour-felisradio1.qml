import QtQuick 2.6
import Sailfish.Silica 1.0
import "pages"
import "cover"

ApplicationWindow {
    allowedOrientations: Orientation.Portrait
    Backend { id: bridge }
    SystemPlayer { backend: bridge }
    initialPage: Component { MainPage { backend: bridge } }
    cover: Component { CoverPage { backend: bridge } }
}
