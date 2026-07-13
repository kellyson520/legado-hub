import { useState } from 'react'
import { Search, BookOpen, User, List, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { testApi, sourcesApi } from '@/api'
import { toast } from 'sonner'

export default function SearchTestPage() {
  const [keyword, setKeyword] = useState('斗罗大陆')
  const [sourceUrl, setSourceUrl] = useState('')
  const [sources, setSources] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [selectedBook, setSelectedBook] = useState<any>(null)
  const [chapters, setChapters] = useState<any[]>([])
  const [tocLoading, setTocLoading] = useState(false)
  const [tocDialogOpen, setTocDialogOpen] = useState(false)
  const [contentDialogOpen, setContentDialogOpen] = useState(false)
  const [selectedChapter, setSelectedChapter] = useState<any>(null)
  const [content, setContent] = useState<any>(null)
  const [contentLoading, setContentLoading] = useState(false)

  async function loadSources() {
    try {
      const res = await sourcesApi.listBookSources({
        page: 1,
        pageSize: 50,
        enabledOnly: true,
      })
      setSources(res.data || [])
    } catch (e) {
      console.error('加载书源失败:', e)
    }
  }

  useState(() => {
    loadSources()
  })

  async function handleSearch() {
    if (!sourceUrl) {
      toast.error('请选择书源')
      return
    }
    if (!keyword.trim()) {
      toast.error('请输入搜索关键词')
      return
    }

    setLoading(true)
    setResults([])
    try {
      const res = await testApi.search(sourceUrl, keyword)
      if (res.success) {
        setResults(res.data?.results || [])
        toast.success(`搜索成功，共 ${res.data?.count || 0} 条结果`)
      } else {
        toast.error(res.message || '搜索失败')
      }
    } catch (e: any) {
      toast.error('搜索失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleGetToc(book: any) {
    setSelectedBook(book)
    setTocLoading(true)
    setChapters([])
    setTocDialogOpen(true)
    try {
      const res = await testApi.toc(sourceUrl, book.bookUrl)
      if (res.success) {
        setChapters(res.data?.chapters || [])
      } else {
        toast.error(res.message || '获取目录失败')
      }
    } catch (e: any) {
      toast.error('获取目录失败: ' + e.message)
    } finally {
      setTocLoading(false)
    }
  }

  async function handleGetContent(chapter: any) {
    setSelectedChapter(chapter)
    setContentLoading(true)
    setContent(null)
    setContentDialogOpen(true)
    try {
      const res = await testApi.content(sourceUrl, chapter.url)
      if (res.success) {
        setContent(res.data)
      } else {
        toast.error(res.message || '获取正文失败')
      }
    } catch (e: any) {
      toast.error('获取正文失败: ' + e.message)
    } finally {
      setContentLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">搜索测试</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row">
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm sm:max-w-xs"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
            >
              <option value="">选择书源...</option>
              {sources.map((s) => (
                <option key={s.bookSourceUrl} value={s.bookSourceUrl}>
                  {s.bookSourceName}
                </option>
              ))}
            </select>
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="输入书名搜索..."
                className="pl-8"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Button onClick={handleSearch} disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              搜索
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            搜索结果 ({results.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              暂无搜索结果
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {results.map((book, idx) => (
                <Card key={idx} className="overflow-hidden">
                  <CardContent className="p-4">
                    <div className="flex gap-3">
                      {book.coverUrl && (
                        <img
                          src={book.coverUrl}
                          alt={book.name}
                          className="h-24 w-16 flex-shrink-0 rounded object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold truncate">{book.name}</h3>
                        <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
                          <User className="h-3 w-3" />
                          {book.author || '未知'}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {book.intro || '暂无简介'}
                        </p>
                        {book.lastChapter && (
                          <p className="mt-1 text-xs">
                            <Badge variant="outline" className="truncate max-w-full">
                              {book.lastChapter}
                            </Badge>
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        onClick={() => handleGetToc(book)}
                      >
                        <List className="mr-1 h-3 w-3" />
                        目录
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* TOC Dialog */}
      <Dialog open={tocDialogOpen} onOpenChange={setTocDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {selectedBook?.name || '目录'}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                共 {chapters.length} 章
              </span>
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto">
            {tocLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : chapters.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                暂无章节
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">序号</TableHead>
                    <TableHead>章节名称</TableHead>
                    <TableHead className="w-20 text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {chapters.map((chapter) => (
                    <TableRow key={chapter.index}>
                      <TableCell>{chapter.index + 1}</TableCell>
                      <TableCell className="truncate max-w-xs">
                        {chapter.title}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleGetContent(chapter)}
                        >
                          查看
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Content Dialog */}
      <Dialog open={contentDialogOpen} onOpenChange={setContentDialogOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{selectedChapter?.title || '正文'}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto">
            {contentLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : !content ? (
              <div className="text-center py-12 text-muted-foreground">
                暂无内容
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex gap-4 text-sm text-muted-foreground">
                  <span>字数: {content.wordCount}</span>
                  {content.title && <span>标题: {content.title}</span>}
                </div>
                <div className="whitespace-pre-wrap rounded-lg bg-muted/30 p-4 text-sm leading-relaxed">
                  {content.content}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
