import { useEffect, useState } from 'react'
import { Plus, Search, Trash2, Edit, Upload, Download, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { sourcesApi, type BookSource } from '@/api'
import { toast } from 'sonner'

export default function SourcesPage() {
  const [sources, setSources] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<any>(null)
  const [sourceJson, setSourceJson] = useState('')

  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importText, setImportText] = useState('')

  useEffect(() => {
    loadSources()
  }, [page, search])

  async function loadSources() {
    setLoading(true)
    try {
      const res = await sourcesApi.listBookSources({
        page,
        pageSize,
        search: search || undefined,
      })
      setSources(res.data || [])
      setTotal(res.total || 0)
    } catch (e: any) {
      toast.error('加载书源失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleEdit(source: any) {
    setEditingSource(source)
    setSourceJson(JSON.stringify(source, null, 2))
    setEditDialogOpen(true)
  }

  function handleAdd() {
    setEditingSource(null)
    setSourceJson(
      JSON.stringify(
        {
          bookSourceName: '',
          bookSourceUrl: '',
          bookSourceGroup: '',
          searchUrl: '',
          ruleSearch: {},
          ruleToc: {},
          ruleContent: {},
          ruleBookInfo: {},
          enabled: true,
        },
        null,
        2
      )
    )
    setEditDialogOpen(true)
  }

  async function handleSave() {
    try {
      const parsed = JSON.parse(sourceJson)
      if (editingSource) {
        await sourcesApi.updateBookSource(
          editingSource.bookSourceUrl,
          parsed
        )
        toast.success('书源更新成功')
      } else {
        await sourcesApi.createBookSource(parsed)
        toast.success('书源创建成功')
      }
      setEditDialogOpen(false)
      loadSources()
    } catch (e: any) {
      toast.error('保存失败: ' + e.message)
    }
  }

  async function handleDelete(url: string) {
    if (!confirm('确定要删除这个书源吗？')) return
    try {
      await sourcesApi.deleteBookSource(url)
      toast.success('删除成功')
      loadSources()
    } catch (e: any) {
      toast.error('删除失败: ' + e.message)
    }
  }

  async function handleImport() {
    try {
      const sources = JSON.parse(importText)
      const sourceList = Array.isArray(sources) ? sources : [sources]
      await sourcesApi.importBookSources(sourceList)
      toast.success(`成功导入 ${sourceList.length} 个书源`)
      setImportDialogOpen(false)
      setImportText('')
      loadSources()
    } catch (e: any) {
      toast.error('导入失败: ' + e.message)
    }
  }

  async function handleExport() {
    try {
      const res = await sourcesApi.listBookSources({ page: 1, pageSize: 1000 })
      const data = res.data || []
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'sources.json'
      a.click()
      URL.revokeObjectURL(url)
      toast.success('导出成功')
    } catch (e: any) {
      toast.error('导出失败: ' + e.message)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <Card>
        <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 items-center gap-2">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索书源名称、URL..."
                className="pl-8"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
              />
            </div>
            <Button variant="ghost" size="icon" onClick={loadSources}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setImportDialogOpen(true)}>
              <Upload className="mr-2 h-4 w-4" />
              导入
            </Button>
            <Button variant="outline" onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />
              导出
            </Button>
            <Button onClick={handleAdd}>
              <Plus className="mr-2 h-4 w-4" />
              新增
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>书源名称</TableHead>
                <TableHead>分组</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>启用</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8">
                    加载中...
                  </TableCell>
                </TableRow>
              ) : sources.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8">
                    暂无书源数据
                  </TableCell>
                </TableRow>
              ) : (
                sources.map((source) => (
                  <TableRow key={source.bookSourceUrl}>
                    <TableCell>
                      <div className="font-medium">{source.bookSourceName}</div>
                      <div className="text-xs text-muted-foreground truncate max-w-xs">
                        {source.bookSourceUrl}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{source.bookSourceGroup || '未分组'}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={source.status === 'ok' ? 'success' : source.status === 'error' ? 'destructive' : 'outline'}>
                        {source.status === 'ok' ? '正常' : source.status === 'error' ? '异常' : '未检测'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={source.enabled ? 'success' : 'outline'}>
                        {source.enabled ? '启用' : '禁用'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleEdit(source)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(source.bookSourceUrl)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t p-4">
            <div className="text-sm text-muted-foreground">
              共 {total} 条，第 {page}/{totalPages} 页
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{editingSource ? '编辑书源' : '新增书源'}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto py-4">
            <Textarea
              value={sourceJson}
              onChange={(e) => setSourceJson(e.target.value)}
              className="min-h-[400px] font-mono text-xs"
              placeholder="请输入 JSON 格式的书源配置"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSave}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Dialog */}
      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>导入书源</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto py-4">
            <Textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              className="min-h-[300px] font-mono text-xs"
              placeholder="请粘贴 Legado 格式的 JSON 书源数组..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleImport}>导入</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
