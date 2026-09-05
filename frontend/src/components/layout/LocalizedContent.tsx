import { cloneElement, isValidElement, Children, type ReactNode, type ReactElement } from 'react'

import { useLanguage } from '@/app/providers/LanguageProvider'

// These props contain user-facing copy on the shared controls. Unknown values
// are intentionally returned unchanged by `t`, so API data and business names
// remain intact while fixed status/error messages still follow the locale.
const translatedProps = new Set(['aria-label', 'aria-description', 'title', 'placeholder', 'message'])

export function LocalizedContent({ children }: { children: ReactNode }) {
  const { t } = useLanguage()

  function localize(node: ReactNode): ReactNode {
    if (typeof node === 'string') return t(node)
    if (!isValidElement(node)) return node

    const element = node as ReactElement<Record<string, unknown>>
    const nextProps: Record<string, unknown> = { ...element.props }
    for (const prop of translatedProps) {
      if (typeof nextProps[prop] === 'string') nextProps[prop] = t(nextProps[prop] as string)
    }
    if (Object.prototype.hasOwnProperty.call(nextProps, 'children')) {
      const localizedChildren = Children.map(nextProps.children as ReactNode, localize)
      nextProps.children = localizedChildren && localizedChildren.length === 1 ? localizedChildren[0] : localizedChildren
    }
    return cloneElement(element, nextProps)
  }

  return <>{Children.map(children, localize)}</>
}
