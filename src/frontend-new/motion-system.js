const motion = () => window.Motion
const systemReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

export function isMotionReduced() {
  return document.documentElement.dataset.reduceMotion === 'true' || systemReducedMotion.matches
}

export function setUserReducedMotion(reduced) {
  document.documentElement.dataset.reduceMotion = reduced ? 'true' : 'false'
}

function animate(target, keyframes, options) {
  if (isMotionReduced() || !target || !motion()?.animate) return null
  try {
    return motion().animate(target, keyframes, options)
  } catch {
    return null
  }
}

export function animatePageEnter(root) {
  if (!root) return
  const targets = [...root.querySelectorAll(':scope > *, .workspace-page > *')]
    .filter((node, index, nodes) => nodes.indexOf(node) === index)
    .slice(0, 9)
  targets.forEach((node) => node.setAttribute('data-motion-page', ''))
  const delay = motion()?.stagger ? motion().stagger(0.018) : 0
  animate(targets, { opacity: [0, 1], transform: ['translateY(5px)', 'translateY(0)'] }, {
    duration: 0.2,
    delay,
    ease: [0.22, 1, 0.36, 1],
  })
}

export function animateNavSelection(item) {
  animate(item?.querySelector('.nav-icon'), { transform: ['translateX(-2px)', 'translateX(0)'], opacity: [0.72, 1] }, {
    duration: 0.16,
    ease: 'ease-out',
  })
}

export function animateSelection(item) {
  animate(item, { transform: ['scale(0.996)', 'scale(1)'], opacity: [0.82, 1] }, {
    duration: 0.17,
    ease: 'ease-out',
  })
}

export async function animateDisclosure(trigger, panel) {
  if (!trigger || !panel) return
  const expanding = trigger.getAttribute('aria-expanded') !== 'true'
  trigger.setAttribute('aria-expanded', String(expanding))
  const icon = trigger.querySelector('svg')

  if (isMotionReduced()) {
    panel.hidden = !expanding
    return
  }

  if (expanding) panel.hidden = false
  const height = panel.scrollHeight
  const panelAnimation = animate(panel, {
    height: expanding ? ['0px', `${height}px`] : [`${height}px`, '0px'],
    opacity: expanding ? [0, 1] : [1, 0],
  }, { duration: 0.18, ease: [0.22, 1, 0.36, 1] })
  animate(icon, { transform: expanding ? ['rotate(180deg)', 'rotate(0deg)'] : ['rotate(0deg)', 'rotate(180deg)'] }, {
    duration: 0.16,
    ease: 'ease-out',
  })
  if (panelAnimation?.finished) await panelAnimation.finished.catch(() => {})
  panel.style.height = ''
  if (!expanding) panel.hidden = true
}

export function animateModalOpen(backdrop, panel) {
  animate(backdrop, { opacity: [0, 1] }, { duration: 0.16, ease: 'ease-out' })
  animate(panel, { opacity: [0, 1], transform: ['translateY(10px) scale(0.995)', 'translateY(0) scale(1)'] }, {
    duration: 0.22,
    ease: [0.22, 1, 0.36, 1],
  })
}

export async function animateModalClose(backdrop, panel) {
  const panelAnimation = animate(panel, { opacity: [1, 0], transform: ['translateY(0) scale(1)', 'translateY(7px) scale(0.997)'] }, {
    duration: 0.14,
    ease: 'ease-in',
  })
  animate(backdrop, { opacity: [1, 0] }, { duration: 0.14, ease: 'ease-in' })
  if (panelAnimation?.finished) await panelAnimation.finished.catch(() => {})
}

export async function animateRowRemoval(row) {
  if (!row || isMotionReduced()) return
  const animation = animate(row, {
    opacity: [1, 0],
    height: [`${row.offsetHeight}px`, '0px'],
    transform: ['translateX(0)', 'translateX(-8px)'],
    paddingTop: [`${parseFloat(getComputedStyle(row).paddingTop)}px`, '0px'],
    paddingBottom: [`${parseFloat(getComputedStyle(row).paddingBottom)}px`, '0px'],
  }, { duration: 0.2, ease: [0.4, 0, 1, 1] })
  if (animation?.finished) await animation.finished.catch(() => {})
}

export function animateToast(toast) {
  animate(toast, { opacity: [0, 1], transform: ['translate(-50%, 8px)', 'translate(-50%, 0)'] }, {
    duration: 0.18,
    ease: 'ease-out',
  })
}

export function animateSettingPreview(preview) {
  animate(preview, { opacity: [0.72, 1], transform: ['translateY(2px)', 'translateY(0)'] }, {
    duration: 0.16,
    ease: 'ease-out',
  })
}

export function animateRefresh(button) {
  animate(button?.querySelector('svg'), { transform: ['rotate(0deg)', 'rotate(180deg)'] }, {
    duration: 0.28,
    ease: 'ease-in-out',
  })
}
