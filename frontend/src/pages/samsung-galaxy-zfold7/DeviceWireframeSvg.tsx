/** 示意用线稿：圆角外轮廓 + 折痕 + 三摄模组，非官方制图。 */
export function DeviceWireframeSvg({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 280"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <linearGradient id="wfStroke" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0d9488" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#0f766e" stopOpacity="0.75" />
        </linearGradient>
      </defs>
      <rect
        x="18"
        y="24"
        width="164"
        height="232"
        rx="22"
        ry="22"
        stroke="url(#wfStroke)"
        strokeWidth="2.2"
      />
      <rect x="34" y="42" width="132" height="196" rx="10" stroke="#94a3b8" strokeWidth="1.2" opacity="0.55" />
      <line x1="100" y1="42" x2="100" y2="238" stroke="#0d9488" strokeWidth="1" strokeDasharray="4 5" opacity="0.45" />
      <rect x="128" y="48" width="44" height="52" rx="12" stroke="url(#wfStroke)" strokeWidth="1.6" />
      <circle cx="150" cy="64" r="5" stroke="#64748b" strokeWidth="1.2" />
      <circle cx="138" cy="78" r="4" stroke="#64748b" strokeWidth="1.1" />
      <circle cx="158" cy="82" r="4" stroke="#64748b" strokeWidth="1.1" />
      <rect x="88" y="252" width="24" height="3" rx="1.5" fill="#cbd5e1" opacity="0.9" />
    </svg>
  );
}
