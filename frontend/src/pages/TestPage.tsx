import { useEffect, useState } from 'react'
import { FlaskConical, Play, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { sourcesApi, testApi } from '@/api'
import { toast } from 'sonner'

export default function TestPage() {
  const [sources, setSources] = useState<any[]>([])
  const [keyword, setKeyword] = useState('斗罗大陆')
  const [testing, setTesting] = useState<Record<string, boolean>>({})
  const [results, setResults] = useState<Record<string, any>>({})

  useEffect(() => {
    loadSources()
  }, [])

  async function loadSources() {
    try {
      const res = await sourcesApi.listBookSources({
        page: 1,
        pageSize: 100,
        enabledOnly: true,
      })
      setSources(res.data || [])
    } catch (e) {
      console.error('加载书源失败:', e)
    }
  }

  async function handleTest(sourceUrl: string) {
    setTesting((prev) => ({ ...prev, [sourceUrl]: true }))
    try {
      const res = await testApi.full(sourceUrl, keyword)
      if (res.success) {
        setResults((prev) => ({ ...prev, [sourceUrl]: res.data }))
        toast.success(`测试完成: ${res.data?.status || ''}`)
      } else {
        toast.error(res.message || '测试失败')
      }
    } catch (e: any) {
      toast.error('测试失败: ' + e.message)
    } finally {
      setTesting((prev) => ({ ...prev, [sourceUrl]: false }))
    }
  }

  async function handleTestAll() {
    for (const source of sources) {
      if (!testing[source.bookSourceUrl]) {
        handleTest(source.bookSourceUrl)
      }
    }
  }

  function getStatusBadge(result: any) {
    if (!result) return <Badge variant="outline">未测试</Badge>
    const score = result.score || 0
    if (score >= 90)
      return <Badge variant="success">完美 {score}</Badge>
    if (score >= 60)
      return <Badge variant="default">良好 {score}</Badge>
    if (score >= 30)
      return <Badge variant="warning">一般 {score}</Badge>
    return <Badge variant="destructive">失败 {score}</Badge>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <FlaskConical className="h-6 w-6 text-primary" />
            <div>
              <h2 className="font-semibold">书源完整测试</h2>
              <p className="text-sm text-muted-foreground">
                测试搜索→目录→正文完整链路，评分书源质量
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="测试关键词"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className="w-40"
            />
            <Button onClick={handleTestAll}>
              <Play className="mr-2 h-4 w-4" />
              全部测试
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Test Results Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>书源名称</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>搜索</TableHead>
                <TableHead>目录</TableHead>
                <TableHead>正文</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((source) => {
                const result = results[source.bookSourceUrl]
                const isTesting = testing[source.bookSourceUrl]
                return (
                  <TableRow key={source.bookSourceUrl}>
                    <TableCell>
                      <div className="font-medium">{source.bookSourceName}</div>
                      <div className="text-xs text-muted-foreground truncate max-w-xs">
                        {source.bookSourceUrl}
                      </div>
                    </TableCell>
                    <TableCell>{getStatusBadge(result)}</TableCell>
                    <TableCell>
                      {result?.search?.success ? (
                        <Badge variant="success" className="gap-1">
                          <CheckCircle className="h-3 w-3" />
                          {result.search.count}
                        </Badge>
                      ) : result ? (
                        <Badge variant="destructive" className="gap-1">
                          <XCircle className="h-3 w-3" />
                        </Badge>
                      ) : (
                        <Badge variant="outline">-</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {result?.toc?.success ? (
                        <Badge variant="success" className="gap-1">
                          <CheckCircle className="h-3 w-3" />
                          {result.toc.count}
                        </Badge>
                      ) : result?.search?.success ? (
                        <Badge variant="destructive" className="gap-1">
                          <XCircle className="h-3 w-3" />
                        </Badge>
                      ) : (
                        <Badge variant="outline">-</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {result?.content?.success ? (
                        <Badge variant="success" className="gap-1">
                          <CheckCircle className="h-3 w-3" />
                          {result.content.wordCount}字
                        </Badge>
                      ) : result?.toc?.success ? (
                        <Badge variant="destructive" className="gap-1">
                          <XCircle className="h-3 w-3" />
                        </Badge>
                      ) : (
                        <Badge variant="outline">-</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleTest(source.bookSourceUrl)}
                        disabled={isTesting}
                      >
                        {isTesting && (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        )}
                        {isTesting ? '测试中' : '测试'}
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
