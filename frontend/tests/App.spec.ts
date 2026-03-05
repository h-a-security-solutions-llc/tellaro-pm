import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'
import router from '@/router'

describe('App', () => {
  it('mounts without error', () => {
    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
      },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
