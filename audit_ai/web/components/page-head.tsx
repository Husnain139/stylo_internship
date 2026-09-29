import type { ReactNode } from "react";

export function PageHead({
  kicker,
  title,
  lede,
  meta,
}: {
  kicker: string;
  title: string;
  lede?: string;
  meta?: ReactNode;
}) {
  return (
    <header className="page-head">
      <p className="kicker">{kicker}</p>
      <div className="page-head-title">
        <h1>{title}</h1>
        {meta}
      </div>
      {lede ? <p className="lede">{lede}</p> : null}
    </header>
  );
}
