import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';

export function HrmDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.getHrmRingDashboard(100);
        setData(res);
      } catch (err) {
        console.error('Failed to fetch HRM dashboard:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="p-8 text-center text-slate-500">Loading metrics...</div>;
  if (!data || data.status === 'no_data') {
    return (
      <div className="p-8 text-center text-slate-500 border border-dashed border-slate-800 rounded-lg">
        No model inference data available in the audit log.
      </div>
    );
  }

  return (
    <div className="space-y-6" data-design-id="hrm-dashboard">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">Execution Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-400">
              {(data.summary.execution_rate * 100).toFixed(1)}%
            </div>
            <p className="text-xs text-slate-500">of total requests</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">Veto Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-400">
              {(data.summary.veto_rate * 100).toFixed(1)}%
            </div>
            <p className="text-xs text-slate-500">by model or gates</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">Avg Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-400">
              {data.summary.avg_latency_ms.toFixed(2)} ms
            </div>
            <p className="text-xs text-slate-500">inference time</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">Total Requests</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">
              {data.summary.total_requests}
            </div>
            <p className="text-xs text-slate-500">last {data.summary.total_requests} samples</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader>
            <CardTitle className="text-lg">Blocked Reasons</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(data.blocked_reasons).length > 0 ? (
                Object.entries(data.blocked_reasons).map(([reason, count]) => (
                  <div key={reason} className="flex items-center justify-between">
                    <span className="text-sm text-slate-300">{reason}</span>
                    <Badge variant="outline" className="bg-slate-800 text-slate-400 border-slate-700">
                      {count as number}
                    </Badge>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500 italic">No blocked signals in current window.</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/50 border-slate-800">
          <CardHeader>
            <CardTitle className="text-lg">Health & Alerts</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-300">Active Version</span>
                <span className="text-sm font-mono text-emerald-400">{data.active_version}</span>
              </div>
              <div className="pt-4">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Active Alerts</h4>
                <div className="space-y-2">
                  {data.alerts.length > 0 ? (
                    data.alerts.map((alert: string) => (
                      <div key={alert} className="p-2 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-medium">
                        ⚠️ {alert}
                      </div>
                    ))
                  ) : (
                    <div className="p-2 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-medium">
                      ✓ ALL SYSTEMS NORMAL
                    </div>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
