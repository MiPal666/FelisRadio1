import QtQuick 2.6
import Amber.Mpris 1.0

Item {
    property var backend
    MprisPlayer {
        serviceName: "harbour_felisradio1"
        identity: "Felis Radio 1"
        desktopEntry: "harbour-felisradio1"
        canControl: true
        canQuit: false
        canRaise: false
        canPlay: backend.ready && !backend.switching
        canPause: backend.ready && (backend.wanted || backend.playing)
        canGoNext: false
        canGoPrevious: false
        canSeek: false
        volume: backend.volume
        onVolumeRequested: backend.setVolume(volume)
        playbackStatus: backend.playing || backend.wanted ? Mpris.Playing : Mpris.Stopped
        metaData.trackId: "/cz/feliscatus/felisradio1/live"
        metaData.title: backend.title
        metaData.contributingArtist: ["Radio 1"]
        metaData.artUrl: Qt.resolvedUrl("images/felisradio1.png")
        onPlayRequested: backend.start()
        // A live station resumes at the live edge, never at a buffered position.
        onPauseRequested: backend.stop()
        onPlayPauseRequested: backend.toggle()
        onStopRequested: backend.stop()
    }
}
