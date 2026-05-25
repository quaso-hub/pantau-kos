/**
 * sounds.js — Professional sound effects untuk dashboard
 * Base64-encoded ultra-short wav untuk instant playback, no HTTP request
 */

// Soft click (UI interaction)
const SOUND_CLICK = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

// Success chime (action completed)
const SOUND_SUCCESS = "data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQ4AAAD//wAA//8AAP//";

// Soft whoosh (card hover / transition)
const SOUND_WHOOSH = "data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQIAAAAAgA==";

// Delete warning
const SOUND_DELETE = "data:audio/wav;base64,UklGRjQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YRAAAAAA//8AAP///wD/";

const audioCache = new Map();
let soundEnabled = localStorage.getItem('god-eye-sound') !== 'false';

function playSound(dataUrl, volume = 0.3) {
  if (!soundEnabled) return;
  try {
    let audio = audioCache.get(dataUrl);
    if (!audio) {
      audio = new Audio(dataUrl);
      audio.volume = volume;
      audioCache.set(dataUrl, audio);
    }
    audio.currentTime = 0;
    audio.play().catch(() => {}); // silent fail
  } catch (e) {}
}

function toggleSound() {
  soundEnabled = !soundEnabled;
  localStorage.setItem('god-eye-sound', soundEnabled);
  playSound(soundEnabled ? SOUND_SUCCESS : SOUND_CLICK, 0.4);
  return soundEnabled;
}

// Export
window.GodEyeSound = {
  click: () => playSound(SOUND_CLICK, 0.2),
  success: () => playSound(SOUND_SUCCESS, 0.35),
  whoosh: () => playSound(SOUND_WHOOSH, 0.15),
  delete: () => playSound(SOUND_DELETE, 0.4),
  toggle: toggleSound,
  enabled: () => soundEnabled,
};
