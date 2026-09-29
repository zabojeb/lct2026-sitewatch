<script lang="ts">
  import { goto } from '$app/navigation';
  import XIcon from 'phosphor-svelte/lib/XIcon';
  import PolygonIcon from 'phosphor-svelte/lib/PolygonIcon';
  import BuildingsIcon from 'phosphor-svelte/lib/BuildingsIcon';
  import CheckCircleIcon from 'phosphor-svelte/lib/CheckCircleIcon';
  import { useSite } from '$lib/site/store.svelte';

  const site = useSite();

  async function markZones(cameraId: string) {
    site.selectCamera(cameraId);
    site.panel = null;
    await goto('/app/site/zones?new=1');
  }
</script>

<aside class="drawer" aria-label="Задачи настройки">
  <header>
    <div>
      <span class="eyebrow">Задачи и настройки</span>
      <h2>Первичная настройка площадки</h2>
    </div>
    <button class="icon-button" onclick={() => (site.panel = null)} aria-label="Закрыть"
      ><XIcon size={20} /></button
    >
  </header>
  <div class="drawer-body">
    {#each site.tasks as task (task.kind + (task.camera?.id ?? ''))}
      {#if task.kind === 'design'}
        <button class="task" onclick={() => ((site.designDialog = true), (site.panel = null))}>
          <BuildingsIcon size={20} />
          <span>
            <b>Загрузить проектный вид</b>
            <small>Ракурс итогового здания для сравнения с кадром камеры</small>
          </span>
          <em>Загрузить →</em>
        </button>
      {:else if task.camera}
        <button class="task" onclick={() => markZones(task.camera!.id)}>
          <PolygonIcon size={20} />
          <span>
            <b>{task.camera.name}</b>
            <small>Выберите технику и обведите область, куда ей нельзя заезжать</small>
          </span>
          <em>Разметить →</em>
        </button>
      {/if}
    {:else}
      <div class="quiet-state">
        <b><CheckCircleIcon size={16} /> Первичная настройка завершена</b>
        <span>Проектный вид загружен, у каждой камеры есть запретные зоны.</span>
      </div>
    {/each}
    <p class="hint">
      Зоны и проектный вид хранятся в этом браузере отдельно для каждого проекта. Алерт о запретной
      зоне появляется, только когда точка касания машины с землёй — низ центра рамки — внутри
      многоугольника, а класс машины для этой зоны запрещён.
    </p>
  </div>
</aside>
