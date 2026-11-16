import QtQuick 2.6
Item {
 enum PlaybackState { StoppedState, PlayingState, PausedState }
 enum Status { NoMedia, Loading, Loaded, Buffering, Stalled, Buffered, EndOfMedia, InvalidMedia }
 property bool autoPlay: false
 property real volume: 1
 property bool muted: false
 property int playbackState: Audio.StoppedState
 property int status: Audio.NoMedia
 property string source: ""
 property real bufferProgress: 0
 property int position: 0
 property bool seekable: false
 signal error(int error, string errorString)
 function play() { playbackState=Audio.PlayingState }
 function pause() { playbackState=Audio.PausedState }
 function stop() { playbackState=Audio.StoppedState }
}
