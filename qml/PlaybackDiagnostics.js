.pragma library

// Position progress is an observation, never proof that PCM reaches a speaker.
function sample(previous, now, position, generation, request, playing) {
    var reset = !previous || previous.generation !== generation || previous.request !== request
            || now < previous.time || position < previous.position
    var elapsed = reset ? 0 : now - previous.time
    var delta = reset ? 0 : position - previous.position
    var stagnant = !reset && playing && previous.playing && delta === 0
            ? previous.stagnant + elapsed : 0
    return {time: now, position: position, generation: generation, request: request,
            playing: playing, elapsed: elapsed, delta: delta, stagnant: stagnant,
            stalled: stagnant >= 5000}
}
