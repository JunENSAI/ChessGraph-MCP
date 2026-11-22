import { useEffect, useState } from 'react'
import { loadPlayerProfile, type PlayerProfile } from '../data/games'

/** The account name for player bars. Falls back to "You" until (or unless) the API answers. */
export function usePlayerProfile(): PlayerProfile & { loaded: boolean } {
  const [profile, setProfile] = useState<PlayerProfile | null>(null)
  useEffect(() => {
    let active = true
    loadPlayerProfile()
      .then(next => {
        if (active) setProfile(next)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])
  return profile ? { ...profile, loaded: true } : { username: 'You', averageRating: null, loaded: false }
}
