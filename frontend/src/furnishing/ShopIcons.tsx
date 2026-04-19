type IconProps = { className?: string };

/** 购物车 */
export function IconCart({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="8" cy="20" r="1.35" fill="currentColor" stroke="none" />
      <circle cx="19" cy="20" r="1.35" fill="currentColor" stroke="none" />
      <path d="M1 2h3l2.4 12.8A2 2 0 0 0 8.35 17h9.3a2 2 0 0 0 1.93-1.47L23 7H6.2" />
    </svg>
  );
}

/** 加入购物车 */
export function IconCartPlus({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="7" cy="19" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="15" cy="19" r="1.15" fill="currentColor" stroke="none" />
      <path d="M1 3h2l1.4 7.8A2 2 0 0 0 6.35 13H16l1.8-5H5" />
      <path d="M18 3v6M15 6h6" />
    </svg>
  );
}

export function IconMinus({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M5 12h14" />
    </svg>
  );
}

export function IconPlus({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
