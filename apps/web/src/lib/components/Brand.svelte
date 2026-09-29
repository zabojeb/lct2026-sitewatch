<script lang="ts">
  let { compact = false } = $props<{ compact?: boolean }>();
</script>

<a href="/" class="brand" aria-label="SiteWatch, главная">
  <span class="brand-mark" aria-hidden="true">SW</span>
  <span class:compact>SITEWATCH</span>
</a>

<style>
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 11px;
    flex-shrink: 0;
    font-size: 18px;
    letter-spacing: -0.05em;
    font-weight: 800;
  }
  .brand-mark {
    background: var(--accent);
    color: var(--accent-ink);
    display: grid;
    place-items: center;
    height: 34px;
    width: 34px;
    font-size: 12px;
    letter-spacing: -0.07em;
  }
  @media (max-width: 400px) {
    .compact {
      display: none;
    }
  }
</style>
