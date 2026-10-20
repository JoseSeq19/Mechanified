/**
 * El logo de Mechanified en el sitio: el emblema y el nombre.
 *
 * El emblema es una imagen (`assets/mechanified-emblema.webp`, sin fondo,
 * pensada para ir sobre negro); el nombre y el lema son texto en Montserrat,
 * la letra del logo, para que se lean nítidos a cualquier tamaño.
 *
 * Es solo del sitio. Dentro de la aplicación la marca es la de la organización
 * (`Marca`), no la de Mechanified.
 */
import emblema from '@/assets/mechanified-emblema.webp';
import { PRODUCTO } from '@/lib/marca';

export function LogoSitio({ conLema = false }: { conLema?: boolean }) {
  return (
    <span className={conLema ? 'mch-sitio-logo mch-sitio-logo--con-lema' : 'mch-sitio-logo'}>
      <img className="mch-sitio-logo__emblema" src={emblema} alt="" width={256} height={256} />
      <span className="mch-sitio-logo__texto">
        <span className="mch-sitio-logo__nombre">{PRODUCTO}</span>
        {conLema && <span className="mch-sitio-logo__lema">Gestión moderna de talleres</span>}
      </span>
    </span>
  );
}
