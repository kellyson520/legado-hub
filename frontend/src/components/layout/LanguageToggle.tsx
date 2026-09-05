import { useLanguage } from '@/app/providers/LanguageProvider'
import { cn } from '@/lib/utils'

export function LanguageToggle({ className }: { className?: string }) {
  const { locale, setLocale, t } = useLanguage()
  const options = [
    { value: 'zh-CN' as const, label: t('common.chinese') },
    { value: 'en-US' as const, label: t('common.english') },
  ]

  return (
    <div
      role="group"
      aria-label={t('common.language')}
      className={cn('inline-flex items-center rounded-md border border-border bg-muted p-0.5', className)}
    >
      {options.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          aria-pressed={locale === value}
          onClick={() => setLocale(value)}
          className={cn(
            'h-7 rounded-[3px] px-2 text-xs font-medium text-muted-foreground transition-colors',
            locale === value && 'bg-card text-foreground shadow-sm'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
