export type NetworkType = 'MNO' | 'IGW' | 'IXP' | 'ISP'

export interface AsnMeta {
  type: NetworkType
  is_mno: boolean
  is_igw: boolean
  foreign_upstreams: { asn: string; path_count: number }[]
  note: string
}

interface Badge {
  label: string
  color: string   // CSS hex for text
  bg: string      // CSS hex for bg
  priority: number
  tooltip: string
}

export const BADGES: Record<NetworkType, Badge> = {
  MNO: {
    label: 'MNO',
    color: '#fca5a5',
    bg: 'rgba(239,68,68,0.15)',
    priority: 1,
    tooltip: 'Mobile Network Operator — serves millions of mobile users directly.',
  },
  IGW: {
    label: 'IGW',
    color: '#fcd34d',
    bg: 'rgba(245,158,11,0.15)',
    priority: 2,
    tooltip: 'International Gateway — carries Myanmar\'s international traffic.',
  },
  IXP: {
    label: 'IXP',
    color: '#93c5fd',
    bg: 'rgba(59,130,246,0.15)',
    priority: 3,
    tooltip: 'Internet Exchange Point — neutral traffic exchange hub.',
  },
  ISP: {
    label: 'ISP',
    color: '#94a3b8',
    bg: 'rgba(148,163,184,0.1)',
    priority: 4,
    tooltip: 'Fixed or wireless ISP — domestic customers only.',
  },
}

export function isCritical(type: NetworkType): boolean {
  return type === 'MNO' || type === 'IGW' || type === 'IXP'
}
