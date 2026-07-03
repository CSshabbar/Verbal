import React, { useState, useEffect, useRef } from 'react';
import {
  View, StyleSheet, TextInput, TouchableOpacity,
  Alert, KeyboardAvoidingView, Platform, Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { Text } from '../components';
import { colors, radius } from '../theme';
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from '../../lib/supabase';
import { getUserId, getDeviceName } from '../../lib/storage';

type Status = 'idle' | 'saving' | 'saved' | 'error' | 'synced';

/**
 * Screen 4c — Canvas. Shared clipboard with real-time sync.
 * Type text or add images — saves to Supabase and syncs to all devices.
 */
export const CanvasScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const [content, setContent] = useState('');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [userId, setUserId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [statusMsg, setStatusMsg] = useState('');
  const [wordCount, setWordCount] = useState(0);

  const inputRef = useRef<TextInput>(null);
  const isRemote = useRef(false);
  const channelRef = useRef<ReturnType<typeof supabase.channel> | null>(null);

  // Init — load data and subscribe to realtime changes
  useEffect(() => {
    let mounted = true;
    (async () => {
      const uid = await getUserId();
      const dn = await getDeviceName();
      if (!mounted) return;
      setUserId(uid);
      setDeviceName(dn);
      await loadCanvas(uid);
      subscribeCanvas(uid, dn);
    })();
    return () => {
      mounted = false;
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
        channelRef.current = null;
      }
    };
  }, []);

  const loadCanvas = async (uid: string) => {
    const { data } = await supabase
      .from('canvas')
      .select('content, image_url')
      .eq('user_id', uid)
      .single();
    if (data) {
      if (data.content) {
        isRemote.current = true;
        setContent(data.content);
        setWordCount(data.content.trim() ? data.content.trim().split(/\s+/).length : 0);
      }
      if (data.image_url) {
        setImageUrl(data.image_url);
        setImageUri(data.image_url);
      }
      if (data.content || data.image_url) {
        showStatus('synced', 'Loaded from cloud');
      }
    }
  };

  const subscribeCanvas = (uid: string, dn: string) => {
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
    }
    console.log('[Canvas] Subscribing to canvas updates for user:', uid);
    const channel = supabase
      .channel(`canvas_${uid}_${Date.now()}`)
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'canvas',
        filter: `user_id=eq.${uid}`,
      }, async (payload) => {
        console.log('[Canvas] Received realtime event:', payload.eventType, payload.new);
        const incoming = (payload.new?.content ?? '') as string;
        const incomingImg = (payload.new?.image_url ?? null) as string | null;
        const fromDevice = (payload.new?.device_name ?? '') as string;
        console.log('[Canvas] Event from device:', fromDevice, 'Current device:', dn);
        if (fromDevice === dn) {
          console.log('[Canvas] Skipping event from same device');
          return;
        }

        isRemote.current = true;
        if (incoming !== undefined) {
          console.log('[Canvas] Updating content from sync');
          setContent(incoming);
          setWordCount(incoming.trim() ? incoming.trim().split(/\s+/).length : 0);
        }
        if (incomingImg !== undefined) {
          console.log('[Canvas] Updating image from sync');
          setImageUrl(incomingImg);
          setImageUri(incomingImg);
        }

        if (incoming) {
          await Clipboard.setStringAsync(incoming);
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showStatus('synced', `↓ From ${fromDevice} · copied to clipboard`);
        } else if (incomingImg) {
          await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          showStatus('synced', `↓ Image from ${fromDevice}`);
        }
      })
      .subscribe((status, err) => {
        console.log('[Canvas] Subscription status:', status);
        if (err) {
          console.error('[Canvas] Subscription error:', err);
        } else {
          console.log('[Canvas] Successfully subscribed to realtime updates');
        }
      });
    channelRef.current = channel;
  };

  const showStatus = (s: Status, msg: string) => {
    setStatus(s);
    setStatusMsg(msg);
    if (s !== 'saving') {
      setTimeout(() => { setStatus('idle'); setStatusMsg(''); }, 3000);
    }
  };

  const handleChange = (text: string) => {
    if (isRemote.current) {
      isRemote.current = false;
      return;
    }
    setContent(text);
    setWordCount(text.trim() ? text.trim().split(/\s+/).length : 0);
    setStatus('idle');
    setStatusMsg('');
  };

  const pickImage = async () => {
    const { status: perm } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm !== 'granted') {
      Alert.alert('Permission needed', 'Allow photo library access in Settings.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      setImageUri(uri);
      setImageUrl(null);
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
  };

  const removeImage = () => {
    setImageUri(null);
    setImageUrl(null);
  };

  const uploadImage = async (localUri: string): Promise<string | null> => {
    try {
      const ext = localUri.split('.').pop()?.split('?')[0]?.toLowerCase() ?? 'jpg';
      const mime = ext === 'png' ? 'image/png' : 'image/jpeg';
      const filename = `${userId}_${Date.now()}.${ext}`;
      const path = `canvas/${filename}`;

      const formData = new FormData();
      formData.append('file', {
        uri: localUri,
        name: filename,
        type: mime,
      } as any);

      const uploadUrl = `${SUPABASE_URL}/storage/v1/object/canvas-images/${path}`;
      const resp = await fetch(uploadUrl, {
        method: 'POST',
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
          'x-upsert': 'true',
        },
        body: formData,
      });

      if (!resp.ok) {
        const errText = await resp.text();
        console.error('Upload error:', resp.status, errText);
        return null;
      }

      const { data } = supabase.storage.from('canvas-images').getPublicUrl(path);
      return data.publicUrl;
    } catch (e) {
      console.error('Upload failed:', e);
      return null;
    }
  };

  const handleSave = async () => {
    if (!userId) {
      Alert.alert('Not configured', 'Set your User ID in Settings first.');
      return;
    }
    console.log('[Canvas] Saving canvas data...', { userId, content, imageUrl, deviceName });
    showStatus('saving', 'Saving…');
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    let finalImageUrl = imageUrl;
    if (imageUri && !imageUrl) {
      showStatus('saving', 'Uploading image…');
      finalImageUrl = await uploadImage(imageUri);
      if (!finalImageUrl) {
        showStatus('error', 'Image upload failed');
        return;
      }
      setImageUrl(finalImageUrl);
    }

    const { data, error } = await supabase.from('canvas').upsert({
      user_id: userId,
      content,
      image_url: finalImageUrl ?? null,
      device_name: deviceName,
      updated_at: new Date().toISOString(),
    }, { onConflict: 'user_id' });

    console.log('[Canvas] Save result:', { data, error });
    if (error) {
      showStatus('error', `Save failed: ${error.message}`);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      return;
    }

    if (content) await Clipboard.setStringAsync(content);
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    showStatus('saved', '✓ Saved & synced');
  };

  const copyImageUrl = async () => {
    if (!imageUrl) return;
    await Clipboard.setStringAsync(imageUrl);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    showStatus('saved', 'Image URL copied to clipboard');
  };

  const handlePaste = async () => {
    const text = await Clipboard.getStringAsync();
    if (!text) {
      Alert.alert('Clipboard is empty');
      return;
    }
    const newContent = content ? `${content}\n\n${text}` : text;
    setContent(newContent);
    setWordCount(newContent.trim() ? newContent.trim().split(/\s+/).length : 0);
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const handleClear = () => {
    Alert.alert('Clear canvas', 'Remove all content on all devices?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear',
        style: 'destructive',
        onPress: async () => {
          setContent('');
          setWordCount(0);
          setImageUri(null);
          setImageUrl(null);
          await supabase.from('canvas').upsert({
            user_id: userId,
            content: '',
            image_url: null,
            device_name: deviceName,
            updated_at: new Date().toISOString(),
          }, { onConflict: 'user_id' });
          await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          showStatus('saved', 'Cleared');
        },
      },
    ]);
  };

  const handleReload = async () => {
    await loadCanvas(userId);
    showStatus('synced', 'Reloaded from cloud');
  };

  const statusColor =
    status === 'saved'  ? colors.online :
    status === 'synced' ? colors.primary :
    status === 'error'  ? colors.primary :
    colors.textSecondary;

  return (
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: insets.top + 10 }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text variant="titleSm">Canvas</Text>
          <Text variant="bodyXs" color={colors.textMuted}>Shared clipboard</Text>
        </View>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.iconBtn} onPress={handleReload}>
            <Ionicons name="refresh-outline" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={handlePaste}>
            <Ionicons name="clipboard-outline" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={pickImage}>
            <Ionicons name="image-outline" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          <TouchableOpacity style={[styles.iconBtn, styles.iconBtnDanger]} onPress={handleClear}>
            <Ionicons name="trash-outline" size={20} color={colors.primary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Status message */}
      {status !== 'idle' && (
        <View style={[styles.statusBar, { borderColor: statusColor }]}>
          <Text variant="bodyXs" color={statusColor}>{statusMsg}</Text>
        </View>
      )}

      {/* Text input */}
      <TextInput
        ref={inputRef}
        value={content}
        onChangeText={handleChange}
        placeholder="Type or paste text here…"
        placeholderTextColor={colors.textSubtle}
        style={styles.textInput}
        multiline
        textAlignVertical="top"
      />

      {/* Word count */}
      <View style={styles.wordCountRow}>
        <Text variant="metaSm" color={colors.textMuted}>{wordCount} words</Text>
      </View>

      {/* Image preview */}
      {imageUri && (
        <View style={styles.imageContainer}>
          <Image source={{ uri: imageUri }} style={styles.imagePreview} resizeMode="cover" />
          <TouchableOpacity style={styles.removeImageBtn} onPress={removeImage}>
            <Ionicons name="close-circle" size={24} color={colors.textPrimary} />
          </TouchableOpacity>
          {imageUrl && (
            <TouchableOpacity style={styles.copyUrlBtn} onPress={copyImageUrl}>
              <Text variant="buttonSm" color={colors.primary}>Copy URL</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Save button */}
      <View style={{ flex: 1 }} />
      <TouchableOpacity
        style={[styles.saveBtn, status === 'saving' && { opacity: 0.6 }]}
        onPress={handleSave}
        disabled={status === 'saving'}
      >
        <Text variant="button" color={colors.primaryInk}>
          {status === 'saving' ? 'Saving…' : 'Save & Sync →'}
        </Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 18,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 8,
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconBtnDanger: {
    backgroundColor: colors.primarySoft,
  },
  statusBar: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.lg,
    borderWidth: 1,
    marginBottom: 14,
  },
  textInput: {
    flex: 1,
    minHeight: 200,
    padding: 16,
    borderRadius: radius.lg,
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    fontSize: 17,
    lineHeight: 25,
    color: colors.textPrimary,
  },
  wordCountRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 8,
    marginBottom: 14,
  },
  imageContainer: {
    position: 'relative',
    marginBottom: 14,
  },
  imagePreview: {
    width: '100%',
    height: 200,
    borderRadius: radius.lg,
    backgroundColor: colors.surface2,
  },
  removeImageBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: colors.bgScreen,
    borderRadius: 12,
    padding: 4,
  },
  copyUrlBtn: {
    position: 'absolute',
    bottom: 8,
    right: 8,
    backgroundColor: colors.bgScreen,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  saveBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 14,
    borderRadius: radius.lg,
    alignItems: 'center',
    marginBottom: 16,
  },
});
