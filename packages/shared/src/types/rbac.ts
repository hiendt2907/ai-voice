export const ROLES = ['admin', 'operator', 'qa', 'viewer'] as const
export type Role = (typeof ROLES)[number]

export const ROLE_PERMISSIONS = {
  admin: ['users:manage', 'cloudfone:config', 'script:publish', 'script:edit', 'calls:view', 'reports:view', 'audit:view'],
  operator: ['campaign:manage', 'calls:monitor', 'calls:handoff', 'calls:view', 'reports:view'],
  qa: ['calls:review', 'calls:score', 'learning:approve', 'calls:view'],
  viewer: ['reports:view', 'calls:view'],
} satisfies Record<Role, string[]>

export type Permission = (typeof ROLE_PERMISSIONS)[Role][number]
