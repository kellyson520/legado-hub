declare module '@novnc/novnc/lib/rfb' {
  export default class RFB {
    constructor(target: HTMLElement, url: string)
    disconnect(): void
  }
}
