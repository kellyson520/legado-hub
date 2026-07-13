import { useState } from 'react'
import { Download, Upload, Copy, FileJson } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { outputApi, sourcesApi } from '@/api'
import { toast } from 'sonner'

export default function ExportPage() {
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [group, setGroup] = useState('')
  const [enabledOnly, setEnabledOnly] = useState(true)

  async function handleExportJson() {
    try {
      const res = await outputApi.getBookSources(group || undefined, enabledOnly)
      const data = res.data || []
      const jsonStr = JSON.stringify(data, null, 2)

      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'legado-sources.json'
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`成功导出 ${Array.isArray(data) ? data.length : 0} 个书源`)
    } catch (e: any) {
      toast.error('导出失败: ' + e.message)
    }
  }

  async function handleCopyLink() {
    const link = `${window.location.origin}/api/output/export.json?enabledOnly=${enabledOnly}`
    try {
      await navigator.clipboard.writeText(link)
      toast.success('订阅链接已复制')
    } catch {
      toast.error('复制失败，请手动复制')
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
    } catch (e: any) {
      toast.error('导入失败: ' + e.message)
    }
  }

  const subscriptionUrl = `${window.location.origin}/api/output/export.json?enabledOnly=${enabledOnly}`

  return (
    <div className="space-y-6">
      {/* 导出 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Download className="h-5 w-5" />
            导出书源
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-muted-foreground">分组筛选</label>
              <Input
                placeholder="全部"
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                className="w-40"
              />
            </div>
            <div className="flex items-end gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enabledOnly}
                  onChange={(e) => setEnabledOnly(e.target.checked)}
                  className="h-4 w-4"
                />
                仅启用的
              </label>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleExportJson}>
              <FileJson className="mr-2 h-4 w-4" />
              导出 JSON
            </Button>
            <Button variant="outline" onClick={handleCopyLink}>
              <Copy className="mr-2 h-4 w-4" />
              复制订阅链接
            </Button>
          </div>

          <div className="rounded-lg bg-muted/30 p-4">
            <p className="mb-2 text-sm font-medium">Legado 订阅地址：</p>
            <code className="block break-all text-xs text-muted-foreground">
              {subscriptionUrl}
            </code>
          </div>
        </CardContent>
      </Card>

      {/* 导入 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-5 w-5" />
            导入书源
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            支持导入 Legado 格式的 JSON 书源文件，可以是单个书源对象或书源数组。
          </p>
          <Button onClick={() => setImportDialogOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            粘贴导入
          </Button>
        </CardContent>
      </Card>

      {/* 使用说明 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">使用说明</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <div>
            <p className="font-medium text-foreground">1. 在阅读 App 中添加订阅</p>
            <p>
              复制上面的订阅链接，在 Legado 阅读 App 的"书源管理" → "网络导入"中粘贴链接即可。
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground">2. 手动导入书源</p>
            <p>
              导出 JSON 文件后，在 Legado 中选择"本地导入"，选择导出的 JSON 文件即可。
            </p>
          </div>
          <div>
            <p className="font-medium text-foreground">3. 书源格式</p>
            <p>
              完全兼容 Legado 书源格式，支持 JSONPath、CSS 选择器、XPath、JS 等多种规则类型。
            </p>
          </div>
        </CardContent>
      </Card>

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
              placeholder="请粘贴 Legado 格式的 JSON 书源数组或单个书源对象..."
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
