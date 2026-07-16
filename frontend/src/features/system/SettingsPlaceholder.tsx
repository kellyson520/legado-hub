export function SettingsPlaceholder({ domain, tab }: { domain: string; tab: string }) {
  return (
    <section className="rounded-md border border-dashed border-border bg-card p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Registered section</p>
      <h2 className="mt-2 text-xl font-semibold text-foreground">{domain} / {tab}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">This namespace is ready for its own independently-versioned controls. It is intentionally separated from Agent policy and provider credentials.</p>
    </section>
  )
}
