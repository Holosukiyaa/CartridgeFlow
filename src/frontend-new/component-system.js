import '/node_modules/@awesome.me/webawesome/dist-cdn/components/switch/switch.js'

export const componentSystem = Object.freeze({
  name: 'Web Awesome',
  version: '3.10.0',
  components: ['wa-switch'],
})

export function whenComponentReady(tagName) {
  return customElements.whenDefined(tagName)
}
