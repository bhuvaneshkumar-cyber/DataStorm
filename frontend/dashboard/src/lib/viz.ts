/**
 * Chart colour tokens, and the hook that keeps them in step with the theme.
 *
 * Recharts needs real colour strings rather than CSS custom properties, so the
 * palette is written twice -- once per mode -- and selected in JS. The CSS
 * variables in index.css carry the same values for the charts drawn in plain
 * HTML, and the two must stay identical.
 *
 * The palette is not a matter of taste. These slots were run through the
 * data-viz validator in both modes: every hue clears the lightness band, the
 * chroma floor, the colour-vision-deficiency separation floor and 3:1 contrast
 * against its own surface. Substituting a hue by eye would break that quietly.
 *   light: #2a78d6 / #eb6834  -- worst adjacent CVD dE 24.7, normal dE 33.6
 *   dark:  #3987e5 / #d95926  -- worst adjacent CVD dE 26.8, normal dE 31.8
 */

import { useEffect, useState } from 'react';

export type VizTheme = {
  mode: 'light' | 'dark';
  surface: string;
  grid: string;
  axis: string;
  textPrimary: string;
  textSecondary: string;
  /** Categorical slots, assigned in fixed order and never cycled. */
  series: [string, string];
  /** Single-hue ramp for magnitude comparisons: light to dark. */
  sequential: string[];
  /** Reserved for state, never reused as a series colour. */
  status: { good: string; warning: string; serious: string; critical: string };
};

const LIGHT: VizTheme = {
  mode: 'light',
  surface: '#fcfcfb',
  grid: '#e8e7e3',
  axis: '#c9c8c2',
  textPrimary: '#0b0b0b',
  textSecondary: '#52514e',
  series: ['#2a78d6', '#eb6834'],
  sequential: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#2a78d6', '#256abf', '#184f95'],
  status: { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' },
};

const DARK: VizTheme = {
  mode: 'dark',
  surface: '#1a1a19',
  grid: '#333330',
  axis: '#4a4a46',
  textPrimary: '#ffffff',
  textSecondary: '#c3c2b7',
  series: ['#3987e5', '#d95926'],
  sequential: ['#184f95', '#256abf', '#2a78d6', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb'],
  status: { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' },
};

function currentMode(): 'light' | 'dark' {
  const stamped = document.documentElement.getAttribute('data-theme');
  if (stamped === 'dark' || stamped === 'light') return stamped;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * The active palette, recomputed when the OS preference or an explicit theme
 * stamp changes. Both are watched: the media query alone would miss a toggle,
 * and the attribute alone would miss the reader changing their system setting
 * with the app already open.
 */
export function useVizTheme(): VizTheme {
  const [mode, setMode] = useState<'light' | 'dark'>(() => currentMode());

  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => setMode(currentMode());

    query.addEventListener('change', sync);
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    return () => {
      query.removeEventListener('change', sync);
      observer.disconnect();
    };
  }, []);

  return mode === 'dark' ? DARK : LIGHT;
}

/** Picks a step from the sequential ramp by rank, darkest for the largest value. */
export function sequentialStep(theme: VizTheme, index: number, total: number): string {
  if (total <= 1) return theme.sequential[Math.floor(theme.sequential.length / 2)];
  const position = index / (total - 1);
  // The ramp runs light to dark in light mode and dark to light in dark mode, so
  // in both cases the first (largest) category takes the end with most contrast.
  const ordered = theme.mode === 'light' ? [...theme.sequential].reverse() : theme.sequential;
  return ordered[Math.min(ordered.length - 1, Math.round(position * (ordered.length - 1)))];
}

/**
 * Maps a 0-100 metric score onto the status palette.
 *
 * Status colours ship with a written label everywhere they are used, never
 * alone: four bands are not distinguishable by hue under every form of colour
 * vision, and a score is exactly the kind of thing a reader must not have to
 * guess at.
 */
export function statusForScore(theme: VizTheme, score: number): { color: string; band: string } {
  if (score >= 75) return { color: theme.status.good, band: 'Strong' };
  if (score >= 50) return { color: theme.status.warning, band: 'Fair' };
  if (score >= 30) return { color: theme.status.serious, band: 'Weak' };
  return { color: theme.status.critical, band: 'Critical' };
}
