<script lang="ts">
  import { onMount } from 'svelte';
  import SunIcon from 'phosphor-svelte/lib/SunIcon';
  import MoonIcon from 'phosphor-svelte/lib/MoonIcon';
  let light = $state(false);
  function setTheme(next: boolean) {
    light = next;
    document.documentElement.dataset.theme = light ? 'light' : 'dark';
    try {
      localStorage.setItem('sitewatch.theme', light ? 'light' : 'dark');
    } catch {
      /* Theme still works in memory. */
    }
  }
  onMount(() => {
    light = document.documentElement.dataset.theme === 'light';
  });
</script>

<button
  class="icon-button"
  aria-label={light ? 'Тёмная тема' : 'Светлая тема'}
  onclick={() => setTheme(!light)}
>
  {#if light}<MoonIcon size={20} />{:else}<SunIcon size={20} />{/if}
</button>
