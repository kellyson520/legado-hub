import { useState } from 'react'
import { HeartPulse, Play, Loader2, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { healthApi } from '@/api'
import { toast } from 'sonner'

export default function HealthPage() {
  const [checking, setChecking] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [summary, setSummary] = useState<{ ok: number; error: number; total: number } | null>(null)

  async function handleCheckAll() {
    setChecking(true)
    try {
      const res = await healthApi.checkAll('book', 50)
      if (res.success) {
        setResults(res.data?.results || [])
        setSummary({
          ok: res.data?.ok || 0,
          error: res.data?.error || 0,
          total: res.data?.total || 0,
        })
        toast.success(
          `检查完成: ${res.data?.ok || 0} 正常, ${res.data?.error || 0} 异常`
        )
      } else {
        toast.error(res.message || '检查失败')
      }
    } catch (e: any) {
      toast.error('检查失败: ' + e.message)
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <HeartPulse className="h-6 w-6 text-emerald-500" />
            <div>
              <h2 className="font-semibold">健康检查</h2>
              <p className="text-sm text-muted-foreground">
                批量检测书源可用性，及时发现异常源
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleCheckAll} disabled={checking}>
              {checking && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <RefreshCw className={cn('mr-2 h-4 w-4', checking && 'animate-spin')} />
              全部检测
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Summary */}
      {summary && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="p-6">
              <div className="text-3xl font-bold">{summary.total}</div>
              <div className="text-sm text-muted-foreground">总书源数</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-6 w-6 text-emerald-500" />
                <span className="text-3xl font-bold text-emerald-500">
                  {summary.ok}
                </span>
              </div>
              <div className="text-sm text-muted-foreground">正常</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center gap-2">
                <XCircle className="h-6 w-6 text-destructive" />
                <span className="text-3xl font-bold text-destructive">
                  {summary.error}
                </span>
              </div>
              <div className="text-sm text-muted-foreground">异常</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>书源名称</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>错误信息</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((r, idx) => (
                  <TableRow key={idx}>
                    <TableCell>
                      <div className="font-medium">{r.sourceName}</div>
                      <div className="text-xs text-muted-foreground truncate max-w-xs">
                        {r.sourceUrl}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {r.sourceType === 'book' ? '书源' : '订阅'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={r.status === 'ok' ? 'success' : 'destructive'}>
                        {r.status === 'ok' ? '正常' : '异常'}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">
                      {r.errorMsg || '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {results.length === 0 && !checking && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <HeartPulse className="mb-4 h-12 w-12 text-muted-foreground/30" />
            <p className="text-muted-foreground">点击"全部检测"开始健康检查</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function cn(...args: any[]) {
  return args.filter(Boolean).join(' ')
}
