// Shared lucide icon map for the sub-brand cosmic glyph. Keyed by PascalCase name so the store
// can carry a string (COSMIC_GLYPHS) and components resolve it to a component. (#logo-follows-name)
import { Orbit, Rocket, Satellite, Star, Sparkles, Telescope, Radar, Radio, Moon, Sun, SunMedium, Globe, Atom, Zap, Compass, Navigation, Wind, Aperture, CircleDot, Send } from 'lucide-vue-next'

export const GLYPHS: Record<string, unknown> = {
  Orbit, Rocket, Satellite, Star, Sparkles, Telescope, Radar, Radio, Moon, Sun, SunMedium, Globe, Atom, Zap, Compass, Navigation, Wind, Aperture, CircleDot, Send,
}
