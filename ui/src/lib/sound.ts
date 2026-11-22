/** Move sounds synthesized with WebAudio: no audio files ship with the app. */
export type MoveSound = 'move' | 'capture' | 'check' | 'castle' | 'end'

/** Which sound a SAN move makes. Mate and game end take precedence over check. */
export function soundFor(san: string, gameOver = false): MoveSound {
  if (gameOver || san.includes('#')) return 'end'
  if (san.includes('+')) return 'check'
  if (san.startsWith('O-O')) return 'castle'
  if (san.includes('x')) return 'capture'
  return 'move'
}

const TONES: Record<MoveSound, { freq: number; duration: number; type: OscillatorType; second?: number }> = {
  move: { freq: 420, duration: 0.07, type: 'triangle' },
  capture: { freq: 260, duration: 0.11, type: 'square' },
  check: { freq: 640, duration: 0.12, type: 'sawtooth', second: 820 },
  castle: { freq: 360, duration: 0.07, type: 'triangle', second: 440 },
  end: { freq: 330, duration: 0.28, type: 'sine', second: 495 },
}

const MUTE_KEY = 'chessgraph:muted'
let context: AudioContext | null = null

export function isMuted(): boolean {
  try {
    return window.localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

export function setMuted(muted: boolean): void {
  try {
    window.localStorage.setItem(MUTE_KEY, muted ? '1' : '0')
  } catch {
    // A blocked store only means the choice is not remembered.
  }
}

export function playSound(sound: MoveSound): void {
  if (isMuted() || typeof window === 'undefined' || !('AudioContext' in window)) return
  try {
    context ??= new AudioContext()
    const tone = TONES[sound]
    const start = context.currentTime
    const notes = tone.second ? [tone.freq, tone.second] : [tone.freq]
    notes.forEach((freq, index) => {
      const osc = context!.createOscillator()
      const gain = context!.createGain()
      const at = start + index * tone.duration * 0.8
      osc.type = tone.type
      osc.frequency.setValueAtTime(freq, at)
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(0.12, at + 0.01)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + tone.duration)
      osc.connect(gain).connect(context!.destination)
      osc.start(at)
      osc.stop(at + tone.duration + 0.02)
    })
  } catch {
    // Audio is decoration; a browser that refuses it changes nothing.
  }
}
