export function hasPermission(permissions: string[] | undefined, permission: string): boolean {
  return (permissions ?? []).includes(permission)
}
