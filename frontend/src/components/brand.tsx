import { cn } from "@/lib/utils";

/** Inline CPC Lab logo (faithful SVG recreation of the brand mark). */
export function Logo({ size = 40, className, withPlate = true }: { size?: number; className?: string; withPlate?: boolean }) {
  return (
    <svg
      viewBox="0 0 580 512"
      width={size * (580 / 512)}
      height={size}
      className={cn("shrink-0", className)}
      role="img"
      aria-label="CPC Lab logo"
    >
      <defs>
        <linearGradient id="lg-ring" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#18A0FB" />
          <stop offset="0.45" stopColor="#4D7CF7" />
          <stop offset="1" stopColor="#B02FF5" />
        </linearGradient>
        <linearGradient id="lg-fold" x1="0" y1="1" x2="0.6" y2="0">
          <stop offset="0" stopColor="#0B57D0" />
          <stop offset="1" stopColor="#4338CA" />
        </linearGradient>
        <linearGradient id="lg-bar1" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#38BDF8" />
          <stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
        <linearGradient id="lg-bar2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#818CF8" />
          <stop offset="1" stopColor="#A855F7" />
        </linearGradient>
        <linearGradient id="lg-mesh" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#2FB6F7" />
          <stop offset="0.5" stopColor="#3E6FF6" />
          <stop offset="1" stopColor="#9333EA" />
        </linearGradient>
        <linearGradient id="lg-chev" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#A855F7" />
          <stop offset="1" stopColor="#D946EF" />
        </linearGradient>
      </defs>
      {withPlate ? <rect x="0" y="0" width="580" height="512" rx="28" fill="#04060F" /> : null}
      <path d="M 363.8 368.1 A 178 178 0 1 1 363.8 163.9" fill="none" stroke="url(#lg-ring)" strokeWidth="64" />
      <path d="M 46 312.1 A 178 178 0 0 1 264.1 94" fill="none" stroke="url(#lg-fold)" strokeWidth="60" opacity="0.92" />
      <g stroke="url(#lg-mesh)" strokeWidth="7" fill="none" strokeLinecap="round" opacity="0.95">
        <line x1="233" y1="262" x2="233" y2="172" />
        <line x1="233" y1="262" x2="176" y2="208" />
        <line x1="233" y1="262" x2="290" y2="202" />
        <line x1="233" y1="262" x2="155" y2="262" />
        <line x1="233" y1="262" x2="308" y2="262" />
        <line x1="233" y1="262" x2="172" y2="316" />
        <line x1="233" y1="262" x2="288" y2="314" />
        <line x1="233" y1="262" x2="236" y2="352" />
        <line x1="233" y1="172" x2="176" y2="208" />
        <line x1="233" y1="172" x2="290" y2="202" />
        <line x1="176" y1="208" x2="155" y2="262" />
        <line x1="290" y1="202" x2="308" y2="262" />
        <line x1="155" y1="262" x2="172" y2="316" />
        <line x1="308" y1="262" x2="288" y2="314" />
        <line x1="172" y1="316" x2="236" y2="352" />
        <line x1="288" y1="314" x2="236" y2="352" />
        <line x1="233" y1="172" x2="236" y2="352" />
        <line x1="176" y1="208" x2="288" y2="314" />
        <line x1="290" y1="202" x2="172" y2="316" />
        <line x1="155" y1="262" x2="290" y2="202" />
        <line x1="308" y1="262" x2="176" y2="208" />
      </g>
      <g stroke="none">
        <circle cx="233" cy="172" r="24" fill="#3E8BF6" />
        <circle cx="176" cy="208" r="21" fill="#4CB4FB" />
        <circle cx="290" cy="202" r="21" fill="#7C4DEB" />
        <circle cx="155" cy="262" r="23" fill="#2FB6F7" />
        <circle cx="308" cy="262" r="21" fill="#9333EA" />
        <circle cx="172" cy="316" r="19" fill="#2F7BF0" />
        <circle cx="288" cy="314" r="19" fill="#8B2CF0" />
        <circle cx="236" cy="352" r="21" fill="#4F63F3" />
        <circle cx="233" cy="262" r="29" fill="#3B72F5" />
      </g>
      <rect x="404" y="202" width="20" height="154" rx="10" fill="url(#lg-bar1)" />
      <rect x="440" y="176" width="28" height="206" rx="13" fill="url(#lg-bar2)" />
      <path d="M 480 224 L 512 262 L 480 300 L 480 274 L 492 262 L 480 250 Z" fill="#7C3AED" />
      <path d="M 506 212 L 544 262 L 506 312 L 506 286 L 522 262 L 506 238 Z" fill="url(#lg-chev)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col leading-tight", className)}>
      <span className="text-sm font-semibold tracking-tight">
        CPC <span className="brand-gradient-text">Lab</span>
      </span>
      <span className="text-2xs text-muted-foreground">Cross-Paradigm Compression</span>
    </div>
  );
}
