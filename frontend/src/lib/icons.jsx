/* Avatar Studio — icon set (stroke, currentColor, 24px grid). */
export function Icon({ d, size = 18, fill = false, stroke = 1.6, children, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={stroke}
         strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {d ? <path d={d} /> : children}
    </svg>
  );
}

export const I = {
  grid:      (p) => <Icon {...p}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></Icon>,
  users:     (p) => <Icon {...p}><circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3 3 0 0 1 0 5.6"/><path d="M17.5 20a5.5 5.5 0 0 0-3-4.9"/></Icon>,
  chat:      (p) => <Icon {...p}><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20.5l1.3-5A8 8 0 1 1 21 12Z"/></Icon>,
  spark:     (p) => <Icon {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.5 6.5l2.5 2.5M15 15l2.5 2.5M17.5 6.5 15 9M9 15l-2.5 2.5"/></Icon>,
  chart:     (p) => <Icon {...p}><path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/></Icon>,
  settings:  (p) => <Icon {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a7.9 7.9 0 0 0 0-3l1.6-1.2-1.6-2.8-1.9.7a7.8 7.8 0 0 0-2.6-1.5L14.5 3h-5l-.4 2.2A7.8 7.8 0 0 0 6.5 6.7l-1.9-.7L3 8.8 4.6 10a7.9 7.9 0 0 0 0 3L3 14.2l1.6 2.8 1.9-.7a7.8 7.8 0 0 0 2.6 1.5L9.5 21h5l.4-2.2a7.8 7.8 0 0 0 2.6-1.5l1.9.7 1.6-2.8Z"/></Icon>,
  plus:      (p) => <Icon {...p}><path d="M12 5v14M5 12h14"/></Icon>,
  search:    (p) => <Icon {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></Icon>,
  send:      (p) => <Icon {...p}><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z"/></Icon>,
  mic:       (p) => <Icon {...p}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></Icon>,
  image:     (p) => <Icon {...p}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="m21 16-4.5-4.5L5 21"/></Icon>,
  globe:     (p) => <Icon {...p}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18Z"/></Icon>,
  eye:       (p) => <Icon {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="2.6"/></Icon>,
  sliders:   (p) => <Icon {...p}><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></Icon>,
  palette:   (p) => <Icon {...p}><path d="M12 3a9 9 0 1 0 0 18c1.3 0 2-1 2-2 0-1.4 1.3-2 2.5-2H18a3 3 0 0 0 3-3c0-5-4-9-9-9Z"/><circle cx="7.5" cy="11" r="1"/><circle cx="11" cy="7.5" r="1"/><circle cx="15.5" cy="9" r="1"/></Icon>,
  message:   (p) => <Icon {...p}><path d="M4 4h16v12H7l-3 3V4Z"/></Icon>,
  play:      (p) => <Icon {...p}><path d="M7 4v16l13-8L7 4Z" fill="currentColor" stroke="none"/></Icon>,
  pause:     (p) => <Icon {...p}><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/></Icon>,
  check:     (p) => <Icon {...p}><path d="M20 6 9 17l-5-5"/></Icon>,
  x:         (p) => <Icon {...p}><path d="M18 6 6 18M6 6l12 12"/></Icon>,
  back:      (p) => <Icon {...p}><path d="M19 12H5M12 19l-7-7 7-7"/></Icon>,
  chevron:   (p) => <Icon {...p}><path d="m9 6 6 6-6 6"/></Icon>,
  dot:       (p) => <Icon {...p}><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/></Icon>,
  bolt:      (p) => <Icon {...p}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/></Icon>,
  clock:     (p) => <Icon {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></Icon>,
  layers:    (p) => <Icon {...p}><path d="m12 2 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 17l9 5 9-5"/></Icon>,
  upload:    (p) => <Icon {...p}><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></Icon>,
  star:      (p) => <Icon {...p}><path d="M12 3.5 14.7 9l6 .9-4.3 4.2 1 6-5.4-2.8L6.6 20l1-6L3.3 9.9l6-.9L12 3.5Z"/></Icon>,
  bell:      (p) => <Icon {...p}><path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8M13.7 21a2 2 0 0 1-3.4 0"/></Icon>,
  copy:      (p) => <Icon {...p}><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></Icon>,
};
