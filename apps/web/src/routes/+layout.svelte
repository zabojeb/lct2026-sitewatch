<script lang="ts">
  import '../app.css';
  import IconContext from 'phosphor-svelte/lib/IconContext';

  let { children } = $props();
</script>

<a class="skip-link" href="#main">К содержимому</a>
<IconContext values={{ 'aria-hidden': true, weight: 'regular' }}>
  {@render children()}
</IconContext>
