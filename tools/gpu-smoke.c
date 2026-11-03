#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <stdio.h>
int main(void){
 ID3D11Device *d=0; ID3D11DeviceContext *c=0; D3D_FEATURE_LEVEL fl;
 HRESULT hr=D3D11CreateDevice(0,D3D_DRIVER_TYPE_HARDWARE,0,0,0,0,D3D11_SDK_VERSION,&d,&fl,&c);
 printf("Hardware D3D11CreateDevice HRESULT=0x%08lx feature=0x%x\n",(unsigned long)hr,fl); if(FAILED(hr))return 1;
 IDXGIDevice *xd=0;IDXGIAdapter *a=0;DXGI_ADAPTER_DESC ad={0};
 ID3D11Device_QueryInterface(d,&IID_IDXGIDevice,(void**)&xd);IDXGIDevice_GetAdapter(xd,&a);IDXGIAdapter_GetDesc(a,&ad);
 printf("Adapter=%ls vendor=%04x device=%04x VRAM=%llu\n",ad.Description,ad.VendorId,ad.DeviceId,(unsigned long long)ad.DedicatedVideoMemory);
 D3D11_TEXTURE2D_DESC t={0};t.Width=16;t.Height=16;t.MipLevels=1;t.ArraySize=1;t.Format=DXGI_FORMAT_R8G8B8A8_UNORM;t.SampleDesc.Count=1;t.Usage=D3D11_USAGE_DEFAULT;t.BindFlags=D3D11_BIND_RENDER_TARGET;
 ID3D11Texture2D *tex=0,*st=0;ID3D11RenderTargetView *rt=0;
 hr=ID3D11Device_CreateTexture2D(d,&t,0,&tex);if(FAILED(hr)){printf("GPU operation 2 HRESULT=0x%08lx\n",(unsigned long)hr);return 2;}
 hr=ID3D11Device_CreateRenderTargetView(d,(ID3D11Resource*)tex,0,&rt);if(FAILED(hr)){printf("GPU operation 3 HRESULT=0x%08lx\n",(unsigned long)hr);return 3;}
 const float color[4]={1,0,0,1};ID3D11DeviceContext_ClearRenderTargetView(c,rt,color);
 t.Usage=D3D11_USAGE_STAGING;t.BindFlags=0;t.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
 hr=ID3D11Device_CreateTexture2D(d,&t,0,&st);if(FAILED(hr)){printf("GPU operation 4 HRESULT=0x%08lx\n",(unsigned long)hr);return 4;}
 ID3D11DeviceContext_CopyResource(c,(ID3D11Resource*)st,(ID3D11Resource*)tex);
 D3D11_MAPPED_SUBRESOURCE m={0};hr=ID3D11DeviceContext_Map(c,(ID3D11Resource*)st,0,D3D11_MAP_READ,0,&m);if(FAILED(hr)){printf("Map=0x%08lx\n",(unsigned long)hr);return 5;}
 unsigned char *p=m.pData;int ok=p[0]==255&&p[1]==0&&p[2]==0&&p[3]==255;
 printf("GPU clear/readback RGBA=%u,%u,%u,%u %s\n",p[0],p[1],p[2],p[3],ok?"PASS":"FAIL");ID3D11DeviceContext_Unmap(c,(ID3D11Resource*)st,0);return ok?0:6;
}
