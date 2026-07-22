import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

const safeProtocols = new Set(['http:', 'https:', 'mailto:'])

function isSafeHref(href: string): boolean {
  try {
    return safeProtocols.has(new URL(href, window.location.origin).protocol)
  } catch {
    return false
  }
}

export function MarkdownMessage({ content, className = '' }: { content: string; className?: string }) {
  return (
    <div className={`prose prose-sm max-w-none break-words text-foreground prose-headings:font-semibold prose-a:text-primary prose-a:underline-offset-4 prose-blockquote:border-primary/40 prose-blockquote:bg-muted/40 prose-blockquote:px-4 prose-blockquote:py-1 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-pre:overflow-x-auto prose-pre:rounded-lg prose-pre:bg-slate-950 prose-pre:text-slate-100 prose-table:my-3 prose-th:bg-muted/60 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-td:align-top ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children, ...props }) => {
            if (!href || !isSafeHref(href)) {
              return <span className="text-muted-foreground">{children}</span>
            }
            return (
              <a
                {...props}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
              >
                {children}
              </a>
            )
          },
          table: ({ children, ...props }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-border">
              <table {...props} className="m-0 min-w-full">{children}</table>
            </div>
          ),
          pre: ({ children, ...props }) => <pre {...props} className="max-h-96 overflow-auto">{children}</pre>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
