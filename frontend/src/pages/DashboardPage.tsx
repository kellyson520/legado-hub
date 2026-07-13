import { useEffect, useState } from 'react'
import {
  BookOpen,
  CheckCircle,
  AlertTriangle,
  Clock,
  TrendingUp,
  Activity,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboardApi } from '@/api'

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStats()
  }, [])

  async function loadStats() {
    try {
      const res = await dashboardApi.getStats()
      setStats(res.data)
    } catch (e) {
      console.error('加载统计失败:', e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">加载中...</div>
      </div>
    )
  }

  const book = stats?.bookSources || {}
  const rss = stats?.rssSources || {}

  const statsCards = [
    {
      title: '书源总数',
      value: book.total || 0,
      icon: BookOpen,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      sub: `启用 ${book.enabled || 0} 个`,
    },
    {
      title: '正常书源',
      value: book.ok || 0,
      icon: CheckCircle,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
      sub: '健康可用',
    },
    {
      title: '异常书源',
      value: book.error || 0,
      icon: AlertTriangle,
      color: 'text-amber-500',
      bgColor: 'bg-amber-500/10',
      sub: '需要检查',
    },
    {
      title: '订阅源',
      value: rss.total || 0,
      icon: Activity,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      sub: `启用 ${rss.enabled || 0} 个`,
    },
  ]

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statsCards.map((card) => (
          <Card key={card.title}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{card.title}</p>
                  <p className="mt-1 text-3xl font-bold">{card.value}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {card.sub}
                  </p>
                </div>
                <div className={cn('rounded-full p-3', card.bgColor)}>
                  <card.icon className={cn('h-6 w-6', card.color)} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">系统信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between">
              <span className="text-muted-foreground">引擎版本</span>
              <span className="font-medium">Legado Engine Pro v2.1.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">架构模式</span>
              <span className="font-medium">DDD 分层架构</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">解析类型</span>
              <span className="font-medium">
                JSONPath / CSS / XPath / JS
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">存储后端</span>
              <span className="font-medium">SQLite</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">快速开始</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                1
              </div>
              <div>
                <p className="font-medium">导入书源</p>
                <p className="text-sm text-muted-foreground">
                  从 Legado 导出的 JSON 文件导入书源
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                2
              </div>
              <div>
                <p className="font-medium">测试书源</p>
                <p className="text-sm text-muted-foreground">
                  使用搜索测试验证书源是否正常工作
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                3
              </div>
              <div>
                <p className="font-medium">订阅使用</p>
                <p className="text-sm text-muted-foreground">
                  在阅读 App 中添加订阅地址使用
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function cn(...args: any[]) {
  return args.filter(Boolean).join(' ')
}
