import { useEffect, useState } from 'react';
import { LivingAppsService } from '@/services/livingAppsService';
import type { Kurse, Anmeldungen, Dozenten, Teilnehmer, Raeume } from '@/types/app';
import { BookOpen, Users, GraduationCap, ClipboardList, TrendingUp, Euro, CheckCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { format, parseISO, isAfter, isBefore, startOfToday } from 'date-fns';
import { de } from 'date-fns/locale';

export default function DashboardOverview() {
  const [kurse, setKurse] = useState<Kurse[]>([]);
  const [anmeldungen, setAnmeldungen] = useState<Anmeldungen[]>([]);
  const [dozenten, setDozenten] = useState<Dozenten[]>([]);
  const [teilnehmer, setTeilnehmer] = useState<Teilnehmer[]>([]);
  const [raeume, setRaeume] = useState<Raeume[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      LivingAppsService.getKurse(),
      LivingAppsService.getAnmeldungen(),
      LivingAppsService.getDozenten(),
      LivingAppsService.getTeilnehmer(),
      LivingAppsService.getRaeume(),
    ]).then(([k, a, d, t, r]) => {
      setKurse(k);
      setAnmeldungen(a);
      setDozenten(d);
      setTeilnehmer(t);
      setRaeume(r);
    }).finally(() => setLoading(false));
  }, []);

  const today = startOfToday();
  const aktiveKurse = kurse.filter(k =>
    k.fields.startdatum && k.fields.enddatum &&
    !isAfter(parseISO(k.fields.startdatum), today) &&
    !isBefore(parseISO(k.fields.enddatum), today)
  );
  const kommendeKurse = kurse.filter(k =>
    k.fields.startdatum && isAfter(parseISO(k.fields.startdatum), today)
  );
  const bezahlt = anmeldungen.filter(a => a.fields.bezahlt).length;
  const ausstehend = anmeldungen.filter(a => !a.fields.bezahlt).length;
  const umsatz = anmeldungen.reduce((sum, a) => {
    const kursId = a.fields.kurs?.match(/([a-f0-9]{24})$/i)?.[1];
    const kurs = kurse.find(k => k.record_id === kursId);
    return sum + (a.fields.bezahlt && kurs?.fields.preis ? kurs.fields.preis : 0);
  }, 0);

  const anmeldungenProKurs = kurse.slice(0, 6).map(k => {
    const count = anmeldungen.filter(a => {
      const id = a.fields.kurs?.match(/([a-f0-9]{24})$/i)?.[1];
      return id === k.record_id;
    }).length;
    return {
      name: k.fields.titel ? (k.fields.titel.length > 16 ? k.fields.titel.slice(0, 16) + '…' : k.fields.titel) : '—',
      anmeldungen: count,
      max: k.fields.max_teilnehmer || 0,
    };
  });

  const pieData = [
    { name: 'Bezahlt', value: bezahlt, color: 'var(--color-chart-3)' },
    { name: 'Ausstehend', value: ausstehend, color: 'var(--color-chart-5)' },
  ].filter(d => d.value > 0);

  const recentAnmeldungen = [...anmeldungen]
    .sort((a, b) => new Date(b.createdat).getTime() - new Date(a.createdat).getTime())
    .slice(0, 5);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-muted-foreground text-sm font-medium">Daten werden geladen…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl gradient-hero p-8" style={{ color: 'oklch(0.98 0 0)' }}>
        <div className="relative z-10">
          <p className="text-xs font-semibold uppercase tracking-[0.15em] mb-2" style={{ opacity: 0.6 }}>Akademie-Management</p>
          <h1 className="font-display text-4xl font-bold mb-1">Guten Morgen</h1>
          <p className="text-sm mt-2" style={{ opacity: 0.7 }}>
            {format(today, "EEEE, d. MMMM yyyy", { locale: de })}
            {aktiveKurse.length > 0 && ` · ${aktiveKurse.length} aktive Kurs${aktiveKurse.length > 1 ? 'e' : ''}`}
          </p>
        </div>
        <div className="absolute right-8 top-1/2 -translate-y-1/2 w-32 h-32 rounded-full border" style={{ borderColor: 'oklch(0.98 0 0 / 0.1)', opacity: 0.3 }} />
        <div className="absolute right-16 top-1/2 -translate-y-1/2 w-52 h-52 rounded-full border" style={{ borderColor: 'oklch(0.98 0 0 / 0.1)', opacity: 0.2 }} />
        <div className="absolute right-4 top-1/2 -translate-y-1/2 w-16 h-16 rounded-full gradient-brand opacity-40 blur-xl" />
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={<BookOpen size={18} />} label="Kurse gesamt" value={kurse.length} sub={`${aktiveKurse.length} aktiv`} accent="stat-brand" />
        <KpiCard icon={<Users size={18} />} label="Teilnehmer" value={teilnehmer.length} sub={`${anmeldungen.length} Anmeldungen`} accent="stat-teal" />
        <KpiCard icon={<GraduationCap size={18} />} label="Dozenten" value={dozenten.length} sub={`${raeume.length} Räume`} accent="stat-green" />
        <KpiCard icon={<Euro size={18} />} label="Umsatz" value={`${umsatz.toLocaleString('de-DE')} €`} sub={`${bezahlt} bezahlt`} accent="stat-amber" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-card rounded-2xl shadow-card p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="font-semibold text-base">Anmeldungen pro Kurs</h2>
              <p className="text-muted-foreground text-xs mt-0.5">Aktuelle Belegung</p>
            </div>
            <span className="badge-brand text-xs font-medium px-2.5 py-1 rounded-full">Top 6</span>
          </div>
          {anmeldungenProKurs.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={anmeldungenProKurs} barSize={28}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: 'var(--color-card)', border: '1px solid var(--color-border)', borderRadius: 10, fontSize: 12 }}
                  cursor={{ fill: 'var(--color-accent)', radius: 4 }}
                />
                <Bar dataKey="anmeldungen" fill="var(--color-chart-1)" radius={[6, 6, 0, 0]} name="Anmeldungen" />
                <Bar dataKey="max" fill="var(--color-chart-1)" fillOpacity={0.18} radius={[6, 6, 0, 0]} name="Max" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState label="Noch keine Kurse angelegt" />
          )}
        </div>

        <div className="bg-card rounded-2xl shadow-card p-6 flex flex-col">
          <div className="mb-6">
            <h2 className="font-semibold text-base">Zahlungsstatus</h2>
            <p className="text-muted-foreground text-xs mt-0.5">Alle Anmeldungen</p>
          </div>
          {pieData.length > 0 ? (
            <>
              <div className="flex-1 flex items-center justify-center">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={72} paddingAngle={3} dataKey="value">
                      {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: 'var(--color-card)', border: '1px solid var(--color-border)', borderRadius: 10, fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex gap-4 justify-center mt-2">
                {pieData.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} />
                    {d.name}: <span className="font-semibold text-foreground">{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState label="Noch keine Anmeldungen" />
          )}
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-card rounded-2xl shadow-card p-6">
          <div className="flex items-center gap-2 mb-5">
            <ClipboardList size={16} className="text-primary" />
            <h2 className="font-semibold text-base">Letzte Anmeldungen</h2>
          </div>
          {recentAnmeldungen.length > 0 ? (
            <div className="space-y-3">
              {recentAnmeldungen.map(a => {
                const teilnehmerId = a.fields.teilnehmer?.match(/([a-f0-9]{24})$/i)?.[1];
                const kursId = a.fields.kurs?.match(/([a-f0-9]{24})$/i)?.[1];
                const tn = teilnehmer.find(t => t.record_id === teilnehmerId);
                const k = kurse.find(kk => kk.record_id === kursId);
                return (
                  <div key={a.record_id} className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full gradient-brand flex items-center justify-center text-xs font-bold flex-shrink-0" style={{ color: 'oklch(0.98 0 0)' }}>
                        {(tn?.fields.name || '?').charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium leading-tight">{tn?.fields.name || '—'}</p>
                        <p className="text-xs text-muted-foreground">{k?.fields.titel || '—'}</p>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${a.fields.bezahlt ? 'badge-paid' : 'badge-unpaid'}`}>
                        {a.fields.bezahlt ? 'Bezahlt' : 'Offen'}
                      </span>
                      {a.fields.anmeldedatum && (
                        <span className="text-xs text-muted-foreground">
                          {format(parseISO(a.fields.anmeldedatum), 'dd.MM.yy')}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState label="Noch keine Anmeldungen" />
          )}
        </div>

        <div className="bg-card rounded-2xl shadow-card p-6">
          <div className="flex items-center gap-2 mb-5">
            <TrendingUp size={16} className="text-primary" />
            <h2 className="font-semibold text-base">Kommende Kurse</h2>
          </div>
          {kommendeKurse.length > 0 ? (
            <div className="space-y-3">
              {kommendeKurse.slice(0, 5).map(k => {
                const anmCount = anmeldungen.filter(a => {
                  const id = a.fields.kurs?.match(/([a-f0-9]{24})$/i)?.[1];
                  return id === k.record_id;
                }).length;
                const fill = k.fields.max_teilnehmer ? Math.round((anmCount / k.fields.max_teilnehmer) * 100) : 0;
                return (
                  <div key={k.record_id} className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
                    <div className="flex-1 min-w-0 mr-4">
                      <p className="text-sm font-medium truncate">{k.fields.titel}</p>
                      <div className="flex items-center gap-2 mt-1">
                        {k.fields.startdatum && (
                          <span className="text-xs text-muted-foreground">
                            {format(parseISO(k.fields.startdatum), 'dd.MM.yyyy')}
                          </span>
                        )}
                        {k.fields.preis != null && (
                          <span className="badge-brand text-xs px-1.5 py-0.5 rounded-full">{k.fields.preis} €</span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="text-xs font-semibold text-foreground">{anmCount}/{k.fields.max_teilnehmer || '∞'}</span>
                      {k.fields.max_teilnehmer ? (
                        <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${Math.min(fill, 100)}%`, background: fill >= 80 ? 'var(--color-chart-5)' : 'var(--color-chart-1)' }}
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState label="Keine bevorstehenden Kurse" />
          )}
        </div>
      </div>

      {/* Summary Footer */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MiniStat icon={<CheckCircle size={14} />} label="Aktive Kurse" value={aktiveKurse.length} />
        <MiniStat icon={<TrendingUp size={14} />} label="Kommende Kurse" value={kommendeKurse.length} />
        <MiniStat icon={<ClipboardList size={14} />} label="Offene Zahlungen" value={ausstehend} />
        <MiniStat icon={<Euro size={14} />} label="Ø Kurs-Preis" value={kurse.length ? `${Math.round(kurse.reduce((s, k) => s + (k.fields.preis || 0), 0) / kurse.length)} €` : '—'} />
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, accent }: { icon: React.ReactNode; label: string; value: string | number; sub?: string; accent: string }) {
  return (
    <div className={`bg-card rounded-2xl shadow-card p-5 ${accent} transition-smooth hover:shadow-md`}>
      <div className="flex items-start justify-between mb-3">
        <div className="w-9 h-9 rounded-xl bg-muted flex items-center justify-center text-primary">
          {icon}
        </div>
      </div>
      <p className="font-display text-2xl font-bold tracking-tight">{value}</p>
      <p className="text-xs font-medium text-foreground mt-0.5">{label}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function MiniStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-card rounded-xl shadow-card px-4 py-3 flex items-center gap-3">
      <span className="text-muted-foreground">{icon}</span>
      <div>
        <p className="text-sm font-bold">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mb-3">
        <BookOpen size={16} />
      </div>
      <p className="text-xs">{label}</p>
    </div>
  );
}
