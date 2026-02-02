import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userApi, krogerApi } from '../api/client'
import { Settings as SettingsIcon, Link, Unlink, MapPin, Loader2, Check, Plus, X } from 'lucide-react'

interface UserSettings {
  pantry_items: string[]
  store_location_id?: string
  store_name?: string
  zip_code?: string
  fulfillment_method: string
  mealie_connected: boolean
}

interface KrogerStatus {
  connected: boolean
  expires_at?: string
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [mealieKey, setMealieKey] = useState('')
  const [zipCode, setZipCode] = useState('')
  const [newPantryItem, setNewPantryItem] = useState('')

  const { data: settings, isLoading: loadingSettings } = useQuery<UserSettings>({
    queryKey: ['settings'],
    queryFn: userApi.getSettings,
  })

  const { data: krogerStatus } = useQuery<KrogerStatus>({
    queryKey: ['krogerStatus'],
    queryFn: krogerApi.getStatus,
  })

  const { data: stores } = useQuery({
    queryKey: ['stores', zipCode],
    queryFn: () => krogerApi.searchStores(zipCode),
    enabled: zipCode.length === 5,
  })

  const updateSettings = useMutation({
    mutationFn: userApi.updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const connectMealie = useMutation({
    mutationFn: userApi.connectMealie,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setMealieKey('')
    },
  })

  const selectStore = useMutation({
    mutationFn: (locationId: string) => krogerApi.selectStore(locationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const startKrogerAuth = useMutation({
    mutationFn: krogerApi.startAuth,
    onSuccess: (data) => {
      window.location.href = data.auth_url
    },
  })

  const disconnectKroger = useMutation({
    mutationFn: krogerApi.disconnect,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['krogerStatus'] })
    },
  })

  const addPantryItem = () => {
    if (!newPantryItem.trim() || !settings) return
    const updatedPantry = [...settings.pantry_items, newPantryItem.trim()]
    updateSettings.mutate({ pantry_items: updatedPantry })
    setNewPantryItem('')
  }

  const removePantryItem = (item: string) => {
    if (!settings) return
    const updatedPantry = settings.pantry_items.filter((i) => i !== item)
    updateSettings.mutate({ pantry_items: updatedPantry })
  }

  if (loadingSettings) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div className="flex items-center gap-3 mb-6">
        <SettingsIcon className="w-8 h-8 text-primary-600" />
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
      </div>

      {/* Kroger Connection */}
      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Kroger Account</h2>

        {krogerStatus?.connected ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-green-600">
              <Check className="w-5 h-5" />
              <span>Connected to Kroger</span>
            </div>
            <button
              onClick={() => disconnectKroger.mutate()}
              className="flex items-center gap-2 text-red-600 hover:text-red-700"
            >
              <Unlink className="w-4 h-4" />
              Disconnect
            </button>
          </div>
        ) : (
          <button
            onClick={() => startKrogerAuth.mutate()}
            disabled={startKrogerAuth.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {startKrogerAuth.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Link className="w-4 h-4" />
            )}
            Connect Kroger Account
          </button>
        )}
      </section>

      {/* Store Selection */}
      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Preferred Store</h2>

        {settings?.store_name ? (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg flex items-center gap-3">
            <MapPin className="w-5 h-5 text-gray-400" />
            <span className="text-gray-900">{settings.store_name}</span>
          </div>
        ) : null}

        <div className="flex gap-3 mb-4">
          <input
            type="text"
            value={zipCode}
            onChange={(e) => setZipCode(e.target.value.replace(/\D/g, '').slice(0, 5))}
            placeholder="Enter ZIP code"
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>

        {stores?.stores?.length > 0 && (
          <div className="space-y-2">
            {stores.stores.map((store: { locationId: string; name?: string; chain?: string; address?: { addressLine1?: string } }) => (
              <button
                key={store.locationId}
                onClick={() => selectStore.mutate(store.locationId)}
                disabled={selectStore.isPending}
                className="w-full p-3 text-left border border-gray-200 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors"
              >
                <p className="font-medium text-gray-900">{store.name || store.chain}</p>
                <p className="text-sm text-gray-500">{store.address?.addressLine1}</p>
              </button>
            ))}
          </div>
        )}

        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Fulfillment Method
          </label>
          <select
            value={settings?.fulfillment_method || 'PICKUP'}
            onChange={(e) => updateSettings.mutate({ fulfillment_method: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          >
            <option value="PICKUP">Pickup</option>
            <option value="DELIVERY">Delivery</option>
          </select>
        </div>
      </section>

      {/* Mealie Connection */}
      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Mealie Account</h2>

        {settings?.mealie_connected ? (
          <div className="flex items-center gap-2 text-green-600">
            <Check className="w-5 h-5" />
            <span>Connected to Mealie</span>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-600">
              Connect your Mealie account to access your recipe library.
              Generate an API key in Mealie: Settings → API Tokens
            </p>
            <div className="flex gap-3">
              <input
                type="password"
                value={mealieKey}
                onChange={(e) => setMealieKey(e.target.value)}
                placeholder="Mealie API Key"
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              />
              <button
                onClick={() => connectMealie.mutate(mealieKey)}
                disabled={connectMealie.isPending || !mealieKey}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {connectMealie.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  'Connect'
                )}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Pantry Items */}
      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Pantry Items</h2>
        <p className="text-sm text-gray-600 mb-4">
          Items you always have on hand. These will be skipped when adding to cart.
        </p>

        <div className="flex gap-3 mb-4">
          <input
            type="text"
            value={newPantryItem}
            onChange={(e) => setNewPantryItem(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addPantryItem()}
            placeholder="Add pantry item..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
          <button
            onClick={addPantryItem}
            disabled={!newPantryItem.trim() || updateSettings.isPending}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {settings?.pantry_items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm"
            >
              {item}
              <button
                onClick={() => removePantryItem(item)}
                className="p-0.5 hover:text-red-600"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
          {settings?.pantry_items.length === 0 && (
            <span className="text-sm text-gray-400">No pantry items added yet</span>
          )}
        </div>
      </section>
    </div>
  )
}
