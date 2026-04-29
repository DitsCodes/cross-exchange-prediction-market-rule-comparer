export function RiskMatrixSkeleton() {
  return (
    <div className="panel overflow-x-auto" aria-busy="true" aria-live="polite">
      <div className="grid min-w-[820px] grid-cols-[2fr,repeat(4,minmax(0,1.1fr)),0.9fr] gap-px bg-[var(--border)]">
        {Array.from({ length: 6 }).map((_, i) => (
          <HeaderCell key={i} />
        ))}
        {Array.from({ length: 3 }).map((_, rowIdx) => (
          <SkeletonRow key={rowIdx} />
        ))}
      </div>
      <span className="sr-only">Running agents — fetching, retrieving, and synthesizing.</span>
    </div>
  );
}

function HeaderCell() {
  return (
    <div className="bg-[var(--panel)] px-3 py-2">
      <div className="skeleton h-3 w-20" />
    </div>
  );
}

function SkeletonRow() {
  return (
    <>
      <div className="bg-[var(--panel)] px-3 py-3">
        <div className="skeleton mb-2 h-2.5 w-16" />
        <div className="skeleton h-3.5 w-3/4" />
      </div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-[var(--panel)] px-3 py-3">
          <div className="skeleton mb-2 h-4 w-16" />
          <div className="skeleton h-2.5 w-5/6" />
        </div>
      ))}
      <div className="bg-[var(--panel)] px-3 py-3">
        <div className="skeleton h-4 w-20" />
      </div>
    </>
  );
}
