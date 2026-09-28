import type { Component } from 'svelte';
import BulldozerIcon from 'phosphor-svelte/lib/BulldozerIcon';
import CraneIcon from 'phosphor-svelte/lib/CraneIcon';
import CraneTowerIcon from 'phosphor-svelte/lib/CraneTowerIcon';
import CylinderIcon from 'phosphor-svelte/lib/CylinderIcon';
import DropIcon from 'phosphor-svelte/lib/DropIcon';
import EngineIcon from 'phosphor-svelte/lib/EngineIcon';
import HammerIcon from 'phosphor-svelte/lib/HammerIcon';
import HardHatIcon from 'phosphor-svelte/lib/HardHatIcon';
import PersonIcon from 'phosphor-svelte/lib/PersonIcon';
import ShovelIcon from 'phosphor-svelte/lib/ShovelIcon';
import TractorIcon from 'phosphor-svelte/lib/TractorIcon';
import TruckIcon from 'phosphor-svelte/lib/TruckIcon';
import TruckTrailerIcon from 'phosphor-svelte/lib/TruckTrailerIcon';

const ICONS: Record<string, Component> = {
  'dump-truck': TruckIcon,
  truck: TruckIcon,
  'garbage-truck': TruckIcon,
  excavator: ShovelIcon,
  roller: CylinderIcon,
  manipulator: CraneIcon,
  'mobile-crane': CraneIcon,
  'tower-crane': CraneTowerIcon,
  mixer: TruckTrailerIcon,
  bulldozer: BulldozerIcon,
  'mini-bulldozer': BulldozerIcon,
  drill: HammerIcon,
  pump: DropIcon,
  loader: EngineIcon,
  'mini-loader': EngineIcon,
  grader: TractorIcon,
  tractor: TractorIcon,
  paver: EngineIcon,
  person: PersonIcon,
  helmet: HardHatIcon,
};

export const equipmentIcon = (slug: string): Component => ICONS[slug] ?? TruckIcon;
