import QtQuick 2.6
import QtMultimedia 5.6
import io.thp.pyotherside 1.5
import "PlaybackDiagnostics.js" as PlaybackDiagnostics

Item {
    id: backend
    property bool diagnosticLogging: typeof diagnosticsEnabled !== "undefined" && diagnosticsEnabled
    property bool ready: false
    property string streamUrl: ""
    property string streamTitle: ""
    property string errorMessage: ""
    property bool metadataAvailable: false
    property bool wanted: false
    property bool buffering: false
    property bool switching: false
    property bool scanning: false
    property bool discoveryFailed: false
    property bool castNetworkKnown: false
    property bool castWifiAvailable: false
    property string castNetworkKey: ""
    property int castNetworkEpoch: 0
    property bool castSelected: false
    property bool disconnected: false
    property bool castLoading: false
    property string deviceId: "local"
    property string outputName: qsTr("This phone")
    property var devices: []
    property int request: 0
    property int switchRequest: 0
    property bool resumeLocal: false
    property bool localRecovering: false
    property bool localRecoveryAttempted: false
    property int localRecoveryRequest: -1
    property real localRecoveryStarted: 0
    property bool localReopenPending: false
    property bool localHasProgress: false
    property bool localNetworkKnown: false
    property bool localNetworkUsable: false
    property string localNetworkSignature: ""
    property real localNetworkChangedAt: 0
    property real localVolume: 1.0
    property bool localMuted: false
    property real castVolume: 1
    property bool castMuted: false
    property string castState: "IDLE"
    readonly property bool playing: castSelected ? castState === "PLAYING" : audio.playbackState === Audio.PlayingState
    readonly property real volume: castSelected ? castVolume : localVolume
    readonly property bool muted: castSelected ? castMuted : localMuted
    readonly property string title: streamTitle.length ? streamTitle : "Radio 1"
    readonly property string stateText: switching ? qsTr("Switching output…") : disconnected ? qsTr("Cast is unavailable")
        : localRecovering ? qsTr("Playback was interrupted. Reconnecting…")
        : buffering ? qsTr("Connecting…") : playing ? qsTr("Playing live") : qsTr("Stopped")

    property string diagnosticBuild: typeof appBuildVersion !== "undefined" ? appBuildVersion : "0.1.0-22"
    property string lastCastStatus: ""
    property int diagnosticAudioSourceGeneration: 0
    property var diagnosticPlaybackSample: null
    function sampleLocalProgress() {
        var current = PlaybackDiagnostics.sample(diagnosticPlaybackSample, Date.now(), audio.position,
            diagnosticAudioSourceGeneration, request, audio.playbackState === Audio.PlayingState)
        diagnosticPlaybackSample = current
        if (diagnosticLogging) console.warn("Felis Radio 1 AudioProgress " + JSON.stringify({timestamp_ms: current.time,
            build: diagnosticBuild, request: request, sourceGeneration: diagnosticAudioSourceGeneration,
            playbackState: audio.playbackState, mediaStatus: audio.status, wanted: wanted,
            bufferProgress: audio.bufferProgress, position_ms: current.position,
            position_delta_ms: current.delta, sample_elapsed_ms: current.elapsed,
            stagnant_ms: current.stagnant, position_stalled: current.stalled}))
        if (current.delta > 0) localHasProgress = true
        if (current.stalled && localHasProgress) beginLocalRecovery("stagnation", current.time)
        tickLocalRecovery(current.time, current.delta)
    }
    function traceLocal(phase, code, message) {
        if (!diagnosticLogging) return
        console.warn("Felis Radio 1 Audio " + JSON.stringify({timestamp_ms: Date.now(),
            build: diagnosticBuild, event: phase, request: request, wanted: wanted,
            castSelected: castSelected, switching: switching,
            playbackState: audio.playbackState, mediaStatus: audio.status,
            bufferProgress: audio.bufferProgress, position: audio.position,
            seekable: audio.seekable, sourcePresent: String(audio.source).length > 0,
            sourceGeneration: diagnosticAudioSourceGeneration,
            retryPending: localReopenPending, retryAttempted: localRecoveryAttempted,
            recovering: localRecovering, networkKnown: localNetworkKnown, networkUsable: localNetworkUsable,
            errorCode: typeof code === "number" ? code : null,
            errorText: message ? String(message).replace(/https?:\/\/[^\s]+/g, "[url]").slice(0, 320) : ""}))
    }
    function traceCast(phase, data) {
        if (!diagnosticLogging) return
        console.warn("Felis Radio 1 QML " + phase + " " + JSON.stringify({
            timestamp_ms: Date.now(),
            build: diagnosticBuild, eventRequest: data && data.request !== undefined ? data.request : null,
            eventRequestType: data ? typeof data.request : "undefined",
            switchRequest: switchRequest, playRequest: request,
            switching: switching, wanted: wanted, castSelected: castSelected,
            castLoading: castLoading, buffering: buffering, castState: castState,
            localPlayback: audio.playbackState, localStatus: audio.status,
            receiverState: data && data.state !== undefined ? data.state : null,
            hasSource: data && data.hasSource !== undefined ? data.hasSource : null,
            volume: data && data.volume !== undefined ? data.volume : null,
            muted: data && data.muted !== undefined ? data.muted : null,
            seekFailure: data && data.seekFailure !== undefined ? data.seekFailure : null,
            localRecoveryPending: localReopenPending, localRecoveryAttempted: localRecoveryAttempted
        }))
    }
    function song() {
        return {videoId: "radio1", title: title, subtitle: "Radio 1", thumbnail: ""}
    }
    function invoke(method, args, callback) {
        python.call("felisradio1.controller." + method, args, callback || function() {})
    }
    function start() {
        traceCast("play.requested", null)
        if (!ready || switching || wanted) return
        wanted = true
        castLoading = castSelected
        buffering = true
        errorMessage = ""
        streamTitle = ""
        metadataAvailable = false
        request += 1
        cancelLocalRecovery()
        invoke("metadata", [true, request])
        if (castSelected) {
            if (disconnected) {
                switching = true
                switchRequest += 1
                invoke("select", [deviceId, song(), switchRequest])
            } else invoke("play", [song(), request])
        } else {
            audio.source = streamUrl
            audio.play()
        }
    }
    function stop() {
        traceCast("stop.begin", null)
        if (!ready) return
        cancelLocalRecovery()
        wanted = false
        castLoading = false
        buffering = false
        switching = false
        resumeLocal = false
        request += 1
        switchRequest += 1
        audio.stop()
        audio.source = ""
        castState = "IDLE"
        invoke("stop", [])
        invoke("metadata", [false, request])
    }
    function toggle() { if (wanted || playing || switching) stop(); else start() }
    function fail(message) {
        stop()
        errorMessage = message
    }
    function scan() {
        traceCast("scan.requested", null)
        if (!ready) return
        if (castNetworkKnown && !castWifiAvailable) {
            devices = []; scanning = false; discoveryFailed = false
            return
        }
        scanning = true
        discoveryFailed = false
        invoke("scan", [])
    }
    function observeCastNetwork(available, key) {
        if (castNetworkKnown && castWifiAvailable === available && castNetworkKey === key) return
        castNetworkKnown = true
        castWifiAvailable = available
        castNetworkKey = key
        castNetworkEpoch += 1
        devices = []; scanning = false; discoveryFailed = false
        if (castSelected) disconnected = true
        if (switching) {
            switchRequest += 1
            switching = false
            resumeLocal = false
            if (!castSelected && wanted && String(audio.source).length) audio.play()
        }
        if (ready) invoke("network", [castNetworkEpoch, available])
    }
    // A single owner for errors, stalled playback and delayed source reopening.
    // Network events only update readiness; they never interrupt healthy audio.
    function observeLocalNetwork(state, now) {
        if (now === undefined) now = Date.now()
        var route = state.route || {}
        var known = !!(state.available && state.valid)
        var usable = known && !state.offlineMode && !!route.connected && !!route.hasIpv4
                && (route.state === "ready" || route.state === "online")
        var signature = JSON.stringify([known, usable, route.type, route.interfaceName, route.hasIpv4])
        if (signature !== localNetworkSignature) {
            localNetworkSignature = signature
            localNetworkChangedAt = now
        }
        localNetworkKnown = known
        localNetworkUsable = usable
    }
    function cancelLocalRecovery() {
        localReopenTimer.stop()
        localReopenPending = false
        localRecovering = false
        localRecoveryAttempted = false
        localRecoveryRequest = -1
        localHasProgress = false
        diagnosticPlaybackSample = null
    }
    function beginLocalRecovery(reason, now) {
        if (now === undefined) now = Date.now()
        if (!ready || !wanted || castSelected || switching || localRecovering) return
        localRecovering = true
        localRecoveryRequest = request
        localRecoveryStarted = now
        localRecoveryAttempted = false
        buffering = true
        errorMessage = ""
        traceLocal("recovery.begin." + reason, null, "")
    }
    function finishLocalRecoveryFailure() {
        traceLocal("recovery.exhausted", null, "")
        cancelLocalRecovery()
        // Local-only failure: never create or command a Cast connection.
        wanted = false
        buffering = false
        request += 1
        audio.stop()
        audio.source = ""
        invoke("metadata", [false, request])
        errorMessage = qsTr("Could not resume playback. Check your connection and press Play.")
    }
    // Reuse the existing progress sampling timer and source-clear/reopen path.
    // One attempt, including a wait for a usable route, within 20 seconds.
    function tickLocalRecovery(now, delta) {
        if (!localRecovering) return
        if (!ready || !wanted || castSelected || switching || localRecoveryRequest !== request) {
            cancelLocalRecovery()
            return
        }
        if (delta > 0 && !localReopenPending && audio.playbackState === Audio.PlayingState) {
            traceLocal("recovery.confirmed", null, "")
            cancelLocalRecovery()
            localHasProgress = true
            buffering = false
            return
        }
        if (now - localRecoveryStarted >= 20000) { finishLocalRecoveryFailure(); return }
        if (localRecoveryAttempted || localReopenPending) return
        if (localNetworkKnown && !localNetworkUsable) return
        if (now - localNetworkChangedAt < 2000) return
        localReopenPending = true
        buffering = true
        traceLocal("recovery.reopen", null, "")
        audio.stop()
        audio.source = ""
        localReopenTimer.restart()
    }
    function handleLocalError(errorText) {
        if (castSelected || !wanted || switching || localReopenPending) return
        if (localRecovering && localRecoveryAttempted) { finishLocalRecoveryFailure(); return }
        beginLocalRecovery("error", Date.now())
    }
    function reopenLocalLiveStream() {
        localReopenPending = false
        if (!ready || !wanted || castSelected || switching || !localRecovering
                || localRecoveryRequest !== request) return
        if (Date.now() - localRecoveryStarted >= 20000) { finishLocalRecoveryFailure(); return }
        if (localNetworkKnown && (!localNetworkUsable || Date.now() - localNetworkChangedAt < 2000)) return
        localRecoveryAttempted = true
        diagnosticPlaybackSample = null
        audio.source = streamUrl
        if (!localRecovering || !wanted || localRecoveryRequest !== request) return
        audio.play()
        traceLocal("recovery.started", null, "")
    }
    function selectOutput(id) {
        traceCast("select.requested", null)
        if (!ready || switching || (id === deviceId && !disconnected)) return
        cancelLocalRecovery()
        switching = true
        errorMessage = ""
        switchRequest += 1
        if (id === "local") invoke("local", [switchRequest])
        else invoke("select", [id, song(), switchRequest])
    }
    function setVolume(value) {
        if (!ready || !isFinite(value)) return
        value = Math.max(0, Math.min(1, value))
        if (castSelected) invoke("command", ["volume", value])
        else localVolume = value
    }
    function setMuted(value) {
        if (!ready) return
        if (castSelected) invoke("command", ["mute", value])
        else localMuted = value
    }

    Audio {
        id: audio
        autoPlay: false
        volume: backend.localVolume
        muted: backend.localMuted
        onPlaybackStateChanged: {
            backend.traceLocal("playback.changed", null, "")
            if (playbackState === Audio.PlayingState && !backend.localRecovering) backend.buffering = false
            if (playbackState === Audio.StoppedState && backend.wanted && !backend.switching && !backend.localReopenPending
                    && !backend.castSelected && status === Audio.EndOfMedia)
                backend.handleLocalError("EndOfMedia")
        }
        onStatusChanged: {
            backend.traceLocal("status.changed", null, "")
            if (!backend.castSelected && backend.wanted && !backend.switching && !backend.localRecovering)
                backend.buffering = status === Audio.Loading || status === Audio.Stalled || status === Audio.Buffering
        }
        onBufferProgressChanged: backend.traceLocal("buffer.changed", null, "")
        onSourceChanged: {
            backend.diagnosticAudioSourceGeneration += 1
            backend.traceLocal("source.changed", null, "")
        }
        Component.onCompleted: backend.traceLocal("object.created", null, "")
        Component.onDestruction: if (backend.diagnosticLogging) console.warn("Felis Radio 1 Audio " + JSON.stringify({
            timestamp_ms: Date.now(), event: "object.destroyed"}))
        onError: {
            backend.traceLocal("error", error, errorString)
            backend.handleLocalError(errorString)
        }
    }
    Loader {
        id: networkDiagnostics
        source: "NetworkDiagnostics.qml"
        onLoaded: {
            item.diagnosticLogging = backend.diagnosticLogging
            item.observed.connect(function(reason) { backend.traceLocal("network." + reason, null, "") })
            item.castNetworkObserved.connect(function(available, key) { backend.observeCastNetwork(available, key) })
            item.connectivityObserved.connect(function(state) { backend.observeLocalNetwork(state) })
            item.snapshot("connman.observer_attached", true)
        }
        onStatusChanged: if (status === Loader.Error) backend.traceLocal("connman.observer_unavailable", null, "")
    }
    Timer {
        interval: 1000
        repeat: true
        running: backend.wanted && !backend.castSelected
        onTriggered: backend.sampleLocalProgress()
    }
    Timer {
        id: localReopenTimer
        interval: 100
        repeat: false
        onTriggered: backend.reopenLocalLiveStream()
    }
    Python {
        id: python
        Component.onCompleted: {
            backend.traceCast("startup", null)
            addImportPath(pythonImportPath)
            addImportPath(pythonVendorPath)
            setHandler("radio_metadata", function(data) {
                if (data.request !== backend.request || !backend.wanted) return
                backend.streamTitle = data.title
                backend.metadataAvailable = data.available
            })
            setHandler("cast_devices", function(data) {
                if (backend.castNetworkKnown && (data.networkEpoch !== backend.castNetworkEpoch || !backend.castWifiAvailable)) return
                backend.devices = data.items
                backend.scanning = data.scanning
                backend.discoveryFailed = data.error
            })
            setHandler("cast_candidate", function(data) {
                backend.traceCast("cast_candidate.received", data)
                if (!backend.switching || data.request !== backend.switchRequest) {
                    backend.traceCast("cast_candidate.ignored", data)
                    return
                }
                backend.resumeLocal = !backend.castSelected && backend.wanted
                backend.traceCast("local.pause.begin", data)
                if (backend.resumeLocal) audio.pause()
                backend.traceCast("local.pause.done", data)
                backend.invoke("commit", [data.request, backend.wanted, backend.request])
                backend.traceCast("cast_candidate.applied", data)
            })
            setHandler("output_selected", function(data) {
                backend.traceCast("output_selected.received", data)
                if (!backend.switching || data.request !== backend.switchRequest) {
                    backend.traceCast("output_selected.ignored", data)
                    return
                }
                if (typeof data.volume === "number") backend.castVolume = data.volume
                if (typeof data.muted === "boolean") backend.castMuted = data.muted
                backend.castSelected = true
                backend.deviceId = data.deviceId
                backend.outputName = data.name
                backend.disconnected = false
                backend.switching = false
                backend.resumeLocal = false
                backend.castLoading = false
                backend.castState = data.active ? data.state : "IDLE"
                backend.buffering = data.active && data.state === "BUFFERING"
                backend.traceCast("local.stop.begin", data)
                audio.stop()
                backend.traceCast("local.stop.done", data)
                audio.source = ""
                backend.traceCast("local.clear.done", data)
                backend.traceCast("output_selected.applied", data)
            })
            setHandler("local_selected", function(data) {
                backend.traceCast("local_selected.received", data)
                if (!backend.switching || data.request !== backend.switchRequest) {
                    backend.traceCast("local_selected.ignored", data)
                    return
                }
                backend.castSelected = false
                backend.deviceId = "local"
                backend.outputName = qsTr("This phone")
                backend.disconnected = false
                backend.switching = false
                backend.castState = "IDLE"
                if (backend.wanted) { backend.buffering = true; audio.source = backend.streamUrl; audio.play() }
                backend.traceCast("local_selected.applied", data)
            })
            setHandler("output_error", function(data) {
                backend.traceCast("output_error.received", data)
                if (!backend.switching || data.request !== backend.switchRequest) {
                    backend.traceCast("output_error.ignored", data)
                    return
                }
                backend.switching = false
                if (data.recovered) {
                    if (backend.resumeLocal && backend.wanted) audio.play()
                    backend.buffering = false
                    backend.errorMessage = qsTr("Could not switch output. The previous output was kept.")
                } else {
                    backend.fail(qsTr("Could not switch output. Select a device and start the radio again."))
                    if (backend.castSelected) backend.disconnected = true
                }
                backend.resumeLocal = false
                backend.traceCast("output_error.applied", data)
            })
            setHandler("cast_play_ready", function(data) {
                if (!backend.castSelected || data.request !== backend.request || !backend.wanted) return
                backend.castLoading = false
                backend.castState = "PLAYING"
                backend.buffering = false
            })
            setHandler("cast_play_error", function(data) {
                if (!backend.castSelected || data.request !== backend.request) return
                backend.fail(qsTr("Cast did not confirm playback. Select the output again."))
                backend.disconnected = true
            })
            setHandler("cast_status", function(data) {
                if (data.networkEpoch !== undefined && data.networkEpoch !== backend.castNetworkEpoch) return
                var signature = JSON.stringify([data.request, data.state, data.hasSource, data.volume, data.muted,
                    backend.request, backend.switching, backend.castLoading, backend.castSelected])
                if (signature !== backend.lastCastStatus) {
                    backend.lastCastStatus = signature
                    backend.traceCast("cast_status.received", data)
                }
                if (!backend.castSelected || data.deviceId !== backend.deviceId) return
                backend.castVolume = data.volume
                backend.castMuted = data.muted
                if (data.request !== backend.request || backend.switching || backend.castLoading || !backend.wanted) return
                backend.castState = data.state
                backend.buffering = data.state === "BUFFERING"
                if (!data.hasSource && !backend.buffering)
                    backend.fail(qsTr("Cast playback has ended."))
            })
            setHandler("cast_lost", function(data) {
                backend.traceCast("cast_lost.received", data)
                if (!backend.castSelected || data.request !== backend.request
                        || (data.networkEpoch !== undefined && data.networkEpoch !== backend.castNetworkEpoch)) return
                backend.fail(qsTr("Connection to Cast was lost."))
                backend.disconnected = true
            })
            setHandler("cast_command_error", function() {
                backend.errorMessage = qsTr("The Cast command failed. Check the device.")
            })
            importModule("felisradio1.controller", function() {
                backend.invoke("initialize", [], function(result) {
                    backend.streamUrl = result.url
                    backend.ready = true
                    if (backend.castNetworkKnown) backend.invoke("network", [backend.castNetworkEpoch, backend.castWifiAvailable])
                })
            })
        }
        onError: {
            backend.traceCast("python.error", null)
            if (backend.ready) backend.stop()
            backend.scanning = false
            backend.errorMessage = qsTr("Backend error: %1").arg(traceback)
        }
    }
    Timer {
        interval: 5000
        repeat: true
        running: backend.diagnosticLogging && (backend.switching || backend.wanted || backend.castSelected)
        onTriggered: backend.traceCast("heartbeat", null)
    }
    Timer {
        interval: 35000
        running: backend.switching
        onTriggered: {
            backend.fail(qsTr("Switching output timed out. Try selecting the device again."))
            if (backend.castSelected) backend.disconnected = true
        }
    }
    Timer {
        interval: 30000
        running: backend.wanted && backend.buffering && !backend.switching && !backend.localRecovering
        onTriggered: backend.fail(qsTr("Connecting to the stream timed out. Try playing again."))
    }
}
